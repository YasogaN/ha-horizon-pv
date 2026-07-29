from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from functools import partial
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FORECAST_DAYS,
    CONF_INITIAL_PEAK_POWER_W,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PANEL_AZIMUTH_DEG,
    CONF_PANEL_TILT_DEG,
    CONF_PV_SENSOR_ENTITY,
    CONF_TIMEZONE,
    DEFAULT_FORECAST_DAYS,
    DOMAIN,
)
from .pv.cold_start import ColdStartPredictor
from .pv.forecast import (
    PvForecastConfig,
    PvForecastPoint,
    PvForecastResult,
    create_pv_forecast,
)
from .pv.learner import DailyLearner
from .pv.predictor import HorizonPredictor
from .pv.sgd import OnlineSGDRegressor
from .pv.standardizer import OnlineStandardizer

_LOGGER = logging.getLogger(__name__)
CACHE_DIR_NAME = "horizon"
CURRENT_VALUE_REFRESH_INTERVAL = timedelta(minutes=1)

INTERVAL_MINUTES = 15
N_FEATURES = 12


class HorizonCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.cache_path = Path(
            hass.config.path(CACHE_DIR_NAME, f"last_forecast_{entry.entry_id}.json")
        )
        self.settings = dict(entry.data)
        self.settings.update(entry.options)

        n_features = N_FEATURES
        sgd = OnlineSGDRegressor(n_features)
        standardizer = OnlineStandardizer(n_features)
        self.predictor = HorizonPredictor(sgd, standardizer, ColdStartPredictor())
        self.predictor.observed_peak_w = self._resolve_peak_w()
        self.predictor.training_days = 0

        self.learner = DailyLearner(
            hass=hass,
            sgd=sgd,
            standardizer=standardizer,
            pv_sensor_entity=str(self.settings.get(CONF_PV_SENSOR_ENTITY, "")),
            observed_peak_w=self.predictor.observed_peak_w,
        )

        self._daily_errors: list[dict[str, Any]] = []
        self._current_value_unsub = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            always_update=False,
        )

    def _resolve_peak_w(self) -> float:
        raw = self.settings.get(CONF_INITIAL_PEAK_POWER_W, "")
        if raw:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
        return 4000.0

    def _forecast_config(self) -> PvForecastConfig:
        return PvForecastConfig(
            latitude=float(self.settings[CONF_LATITUDE]),
            longitude=float(self.settings[CONF_LONGITUDE]),
            timezone=str(self.settings[CONF_TIMEZONE]),
            panel_azimuth_deg=float(self.settings[CONF_PANEL_AZIMUTH_DEG]),
            panel_tilt_deg=float(self.settings[CONF_PANEL_TILT_DEG]),
            forecast_days=int(
                self.settings.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS)
            ),
        )

    def load_state(self) -> None:
        self.learner.load_state()
        self.predictor.sgd = self.learner.sgd
        self.predictor.standardizer = self.learner.standardizer
        self.predictor.training_days = self.learner.training_days
        self.predictor.observed_peak_w = self.learner.observed_peak_w

    async def async_load_cached_data(self) -> None:
        result = await self.hass.async_add_executor_job(
            load_cached_forecast, self.cache_path
        )
        if result is None:
            return
        self.async_set_updated_data(result)

    @callback
    def async_start_current_value_refresh(self) -> None:
        if self._current_value_unsub is not None:
            return
        self._current_value_unsub = async_track_time_interval(
            self.hass,
            self._async_handle_current_value_refresh,
            CURRENT_VALUE_REFRESH_INTERVAL,
        )

    @callback
    def async_stop_current_value_refresh(self) -> None:
        if self._current_value_unsub is None:
            return
        self._current_value_unsub()
        self._current_value_unsub = None

    @callback
    def _async_handle_current_value_refresh(self, now: datetime) -> None:
        self._refresh_current_value(now)

    @callback
    def _refresh_current_value(self, now: datetime | None = None) -> bool:
        data = self.data
        if data is None or not data.forecast_points:
            return False

        current_time = dt_util.as_local(now or dt_util.now()).replace(
            tzinfo=None, second=0, microsecond=0
        )
        first_point = data.forecast_points[0]
        last_point = data.forecast_points[-1]

        if current_time < first_point.timestamp:
            current_time = first_point.timestamp

        if current_time > last_point.timestamp:
            return False

        previous_point = first_point
        next_index = 0
        for index, point in enumerate(data.forecast_points):
            if point.timestamp >= current_time:
                next_index = index
                break
            previous_point = point

        next_point = data.forecast_points[next_index]

        if previous_point.timestamp == next_point.timestamp:
            current_power_w = next_point.pv_power_w
        else:
            interval_seconds = (
                next_point.timestamp - previous_point.timestamp
            ).total_seconds()
            elapsed_seconds = (
                current_time - previous_point.timestamp
            ).total_seconds()
            factor = elapsed_seconds / interval_seconds
            current_power_w = interpolate(
                previous_point.pv_power_w, next_point.pv_power_w, factor
            )

        if (
            data.current_slot == current_time
            and abs(data.current_power_w - current_power_w) < 0.1
        ):
            return False

        remaining_points = data.forecast_points[next_index:]
        remaining_interval_hours = 0.0
        if next_index < len(data.forecast_points):
            next_ts = data.forecast_points[next_index].timestamp
            if next_ts > current_time:
                remaining_interval_hours = (
                    next_ts - current_time
                ).total_seconds() / 3600

        self.async_set_updated_data(
            PvForecastResult(
                generated_at=data.generated_at,
                current_slot=current_time,
                current_power_w=current_power_w,
                total_energy_kwh=(
                    current_power_w * remaining_interval_hours / 1000
                    + sum(p.pv_energy_kwh for p in remaining_points)
                ),
                forecast_points=data.forecast_points,
            )
        )
        return True

    async def async_learn(self) -> None:
        success = await self.learner.async_train_on_yesterday()
        if success:
            self.learner.training_days += 1
            self.learner.last_training_date = (
                dt_util.now() - timedelta(days=1)
            ).strftime("%Y-%m-%d")
            self.learner.save_state()
            self.load_state()
            await self.async_request_refresh()

    async def async_bootstrap(self, days: int | None = None) -> None:
        _LOGGER.info("Starting bootstrap for %s days", days)

    def get_state(self) -> dict[str, Any]:
        return {
            "training_days": self.learner.training_days,
            "last_training_date": self.learner.last_training_date,
            "physics_peak_w": self.predictor.observed_peak_w,
            "prediction_mode": self.predictor.mode,
            "daily_errors": self._daily_errors[-7:],
        }

    async def _async_update_data(self) -> PvForecastResult:
        config = self._forecast_config()
        try:
            result = await self.hass.async_add_executor_job(
                partial(create_pv_forecast, config, self.predictor, now=dt_util.now())
            )
            await self.hass.async_add_executor_job(
                save_cached_forecast, self.cache_path, result
            )
            return result
        except Exception as err:
            _LOGGER.exception("Forecast update failed")
            if self.data is not None:
                raise UpdateFailed(
                    f"Could not update forecast: {err}"
                ) from err
            raise


def save_cached_forecast(path: Path, result: PvForecastResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(
            forecast_result_to_dict(result), separators=(",", ":")
        ),
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_cached_forecast(path: Path) -> PvForecastResult | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return forecast_result_from_dict(payload)
    except Exception:
        _LOGGER.exception("Could not load cached forecast from %s", path)
        return None


def forecast_result_to_dict(result: PvForecastResult) -> dict[str, object]:
    return {
        "generated_at": result.generated_at.isoformat(),
        "current_slot": result.current_slot.isoformat(),
        "current_power_w": result.current_power_w,
        "total_energy_kwh": result.total_energy_kwh,
        "forecast_points": [
            {
                "timestamp": point.timestamp.isoformat(),
                "pv_power_w": point.pv_power_w,
            }
            for point in result.forecast_points
        ],
    }


def forecast_result_from_dict(payload: dict[str, object]) -> PvForecastResult:
    return PvForecastResult(
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        current_slot=datetime.fromisoformat(str(payload["current_slot"])),
        current_power_w=float(payload["current_power_w"]),
        total_energy_kwh=float(payload["total_energy_kwh"]),
        forecast_points=tuple(
            PvForecastPoint(
                timestamp=datetime.fromisoformat(str(point["timestamp"])),
                pv_power_w=float(point["pv_power_w"]),
            )
            for point in payload["forecast_points"]
        ),
    )


def interpolate(start: float, end: float, factor: float) -> float:
    return start + (end - start) * factor
