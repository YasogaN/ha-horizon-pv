"""Data coordinator for PV Forecast Planner."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from datetime import timedelta
from functools import partial
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FORECAST_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODEL_DIR,
    CONF_PANEL_AZIMUTH_DEG,
    CONF_PANEL_TILT_DEG,
    CONF_SECONDARY_FORECAST_MODEL,
    CONF_SAFE_FORECAST_FACTOR,
    CONF_TIMEZONE,
    DEFAULT_SAFE_FORECAST_FACTOR,
    DOMAIN,
)

if TYPE_CHECKING:
    from .load_planner import LoadPlanResult
    from .pv.forecast import PvForecastResult

_LOGGER = logging.getLogger(__name__)
CACHE_DIR_NAME = "pv_forecast_planner"
CURRENT_VALUE_REFRESH_INTERVAL = timedelta(minutes=1)


class PvForecastCoordinator(DataUpdateCoordinator):
    """Coordinate PV forecast refreshes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.cache_path = Path(
            hass.config.path(CACHE_DIR_NAME, f"last_forecast_{entry.entry_id}.json")
        )
        self.load_plan: LoadPlanResult | None = None
        self.load_config_path = Path(hass.config.path(CACHE_DIR_NAME, "loads.yaml"))
        self._current_value_unsub = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )

    @callback
    def async_start_current_value_refresh(self) -> None:
        """Start refreshing the current sensor value from the cached forecast."""
        if self._current_value_unsub is not None:
            return
        self._current_value_unsub = async_track_time_interval(
            self.hass,
            self._async_handle_current_value_refresh,
            CURRENT_VALUE_REFRESH_INTERVAL,
        )
        _LOGGER.info(
            "Started PV current forecast value refresh: interval=%s",
            CURRENT_VALUE_REFRESH_INTERVAL,
        )

    @callback
    def async_stop_current_value_refresh(self) -> None:
        """Stop refreshing the current sensor value."""
        if self._current_value_unsub is None:
            return
        self._current_value_unsub()
        self._current_value_unsub = None

    @callback
    def _async_handle_current_value_refresh(self, now: datetime) -> None:
        """Refresh the current value from the stored forecast curve."""
        self.async_refresh_current_value(now)

    async def async_load_cached_data(self) -> None:
        """Load the last successful forecast from disk."""
        result = await self.hass.async_add_executor_job(
            load_cached_forecast,
            self.cache_path,
        )
        if result is None:
            _LOGGER.info("No cached PV forecast found at %s", self.cache_path)
            return

        self.async_set_updated_data(result)
        self.async_refresh_current_value()
        _LOGGER.info(
            "Loaded cached PV forecast: path=%s, generated_at=%s, points=%s",
            self.cache_path,
            result.generated_at,
            len(result.forecast_points),
        )

    @callback
    def async_refresh_current_value(self, now: datetime | None = None) -> bool:
        """Update current sensor values from the stored forecast points."""
        data = self.data
        if data is None or not data.forecast_points:
            return False

        current_time = dt_util.as_local(now or dt_util.now()).replace(
            tzinfo=None,
            second=0,
            microsecond=0,
        )
        first_point = data.forecast_points[0]
        last_point = data.forecast_points[-1]
        if current_time < first_point.timestamp:
            _LOGGER.debug(
                "PV forecast current value is before first forecast point: "
                "current_time=%s, first_point=%s, generated_at=%s",
                current_time,
                first_point.timestamp,
                data.generated_at,
            )
            current_time = first_point.timestamp
            current_power_w = first_point.pv_power_w
            safe_current_power_w = first_point.safe_pv_power_w
            next_index = 0
        elif current_time > last_point.timestamp:
            _LOGGER.debug(
                "PV forecast current value refresh skipped because forecast is expired: "
                "current_time=%s, last_point=%s, generated_at=%s",
                current_time,
                last_point.timestamp,
                data.generated_at,
            )
            return False
        else:
            previous_point = first_point
            next_point = first_point
            next_index = 0
            for index, point in enumerate(data.forecast_points):
                if point.timestamp >= current_time:
                    next_point = point
                    next_index = index
                    break
                previous_point = point

            if previous_point.timestamp == next_point.timestamp:
                current_power_w = next_point.pv_power_w
                safe_current_power_w = next_point.safe_pv_power_w
            else:
                interval_seconds = (
                    next_point.timestamp - previous_point.timestamp
                ).total_seconds()
                elapsed_seconds = (
                    current_time - previous_point.timestamp
                ).total_seconds()
                factor = elapsed_seconds / interval_seconds
                current_power_w = interpolate(
                    previous_point.pv_power_w,
                    next_point.pv_power_w,
                    factor,
                )
                safe_current_power_w = interpolate(
                    previous_point.safe_pv_power_w,
                    next_point.safe_pv_power_w,
                    factor,
                )

        if (
            current_time == data.current_slot
            and round(current_power_w, 1) == round(data.current_power_w, 1)
            and round(safe_current_power_w, 1) == round(data.safe_current_power_w, 1)
        ):
            return False

        remaining_points = data.forecast_points[next_index:]
        remaining_interval_hours = 0.0
        if next_index < len(data.forecast_points):
            next_timestamp = data.forecast_points[next_index].timestamp
            if next_timestamp > current_time:
                remaining_interval_hours = (
                    next_timestamp - current_time
                ).total_seconds() / 3600

        refreshed = replace(
            data,
            current_slot=current_time,
            current_power_w=current_power_w,
            safe_current_power_w=safe_current_power_w,
            total_energy_kwh=(
                current_power_w * remaining_interval_hours / 1000
                + sum(point.pv_energy_kwh for point in remaining_points)
            ),
            safe_total_energy_kwh=(
                safe_current_power_w * remaining_interval_hours / 1000
                + sum(point.safe_pv_energy_kwh for point in remaining_points)
            ),
        )
        self.async_set_updated_data(refreshed)
        _LOGGER.debug(
            "PV current forecast value interpolated: current_time=%s, current_power_w=%.1f, "
            "safe_current_power_w=%.1f, remaining_energy_kwh=%.3f",
            refreshed.current_slot,
            refreshed.current_power_w,
            refreshed.safe_current_power_w,
            refreshed.total_energy_kwh,
        )
        return True

    async def _async_update_data(self) -> PvForecastResult:
        """Fetch the latest PV forecast."""
        from .pv.forecast import PvForecastConfig, create_pv_forecast

        settings = dict(self.entry.data)
        settings.update(self.entry.options)
        config = PvForecastConfig(
            model_dir=settings[CONF_MODEL_DIR],
            latitude=float(settings[CONF_LATITUDE]),
            longitude=float(settings[CONF_LONGITUDE]),
            timezone=str(settings[CONF_TIMEZONE]),
            panel_azimuth_deg=float(settings[CONF_PANEL_AZIMUTH_DEG]),
            panel_tilt_deg=float(settings[CONF_PANEL_TILT_DEG]),
            forecast_days=int(settings[CONF_FORECAST_DAYS]),
            safe_forecast_factor=float(
                settings.get(CONF_SAFE_FORECAST_FACTOR, DEFAULT_SAFE_FORECAST_FACTOR)
            ),
            secondary_forecast_model=str(settings[CONF_SECONDARY_FORECAST_MODEL]),
        )
        _LOGGER.info(
            "Starting PV forecast update: model_dir=%s, lat=%s, lon=%s, timezone=%s, "
            "forecast_days=%s, safe_factor=%s, secondary_model=%s",
            config.model_dir,
            config.latitude,
            config.longitude,
            config.timezone,
            config.forecast_days,
            config.safe_forecast_factor,
            config.secondary_forecast_model,
        )
        try:
            result = await self.hass.async_add_executor_job(
                partial(create_pv_forecast, config, now=dt_util.now()),
            )
            _LOGGER.info(
                "PV forecast update successful: current_slot=%s, current_power_w=%.1f, "
                "points=%s, total_energy_kwh=%.3f",
                result.current_slot,
                result.current_power_w,
                len(result.forecast_points),
                result.total_energy_kwh,
            )
            await self.hass.async_add_executor_job(
                save_cached_forecast,
                self.cache_path,
                result,
            )
            return result
        except Exception as err:
            _LOGGER.exception("PV forecast update failed")
            if self.data is not None:
                _LOGGER.warning(
                    "Keeping previous PV forecast data after failed update: "
                    "generated_at=%s, points=%s",
                    self.data.generated_at,
                    len(self.data.forecast_points),
                )
            raise UpdateFailed(f"Could not update PV forecast: {err}") from err

    async def async_update_load_plan(self) -> None:
        """Update the basic load plan from the stored forecast."""
        from .load_planner import create_load_plan, load_load_config

        if self.data is None:
            raise UpdateFailed("No PV forecast available for load planning")

        now = dt_util.as_local(dt_util.now()).replace(tzinfo=None, second=0, microsecond=0)
        _LOGGER.info("Starting load plan update: config=%s", self.load_config_path)
        try:
            base_load_w, loads = await self.hass.async_add_executor_job(
                load_load_config,
                self.load_config_path,
            )
            result = await self.hass.async_add_executor_job(
                partial(
                    create_load_plan,
                    forecast_points=self.data.forecast_points,
                    base_load_w=base_load_w,
                    loads=loads,
                    now=now,
                )
            )
        except Exception as err:
            _LOGGER.exception("Load plan update failed")
            raise UpdateFailed(f"Could not update load plan: {err}") from err

        self.load_plan = result
        self.async_set_updated_data(self.data)
        _LOGGER.info(
            "Load plan update successful: loads=%s, forecast_start=%s, forecast_end=%s",
            len(result.planned_loads),
            result.forecast_start,
            result.forecast_end,
        )


def save_cached_forecast(path: Path, result: PvForecastResult) -> None:
    """Save the last successful PV forecast to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(forecast_result_to_dict(result), separators=(",", ":")),
        encoding="utf-8",
    )
    temp_path.replace(path)
    _LOGGER.info(
        "Saved cached PV forecast: path=%s, generated_at=%s, points=%s",
        path,
        result.generated_at,
        len(result.forecast_points),
    )


def load_cached_forecast(path: Path) -> PvForecastResult | None:
    """Load the last successful PV forecast from disk."""
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return forecast_result_from_dict(payload)
    except Exception:
        _LOGGER.exception("Could not load cached PV forecast from %s", path)
        return None


def forecast_result_to_dict(result: PvForecastResult) -> dict[str, object]:
    """Convert a forecast result to JSON-safe data."""
    return {
        "generated_at": result.generated_at.isoformat(),
        "current_slot": result.current_slot.isoformat(),
        "current_power_w": result.current_power_w,
        "safe_current_power_w": result.safe_current_power_w,
        "total_energy_kwh": result.total_energy_kwh,
        "safe_total_energy_kwh": result.safe_total_energy_kwh,
        "forecast_points": [
            {
                "timestamp": point.timestamp.isoformat(),
                "pv_power_w": point.pv_power_w,
                "safe_pv_power_w": point.safe_pv_power_w,
            }
            for point in result.forecast_points
        ],
    }


def interpolate(start: float, end: float, factor: float) -> float:
    """Linearly interpolate between two values."""
    return start + (end - start) * factor


def forecast_result_from_dict(payload: dict[str, object]) -> PvForecastResult:
    """Convert cached JSON-safe data back to a forecast result."""
    from .pv.forecast import PvForecastPoint, PvForecastResult

    return PvForecastResult(
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        current_slot=datetime.fromisoformat(str(payload["current_slot"])),
        current_power_w=float(payload["current_power_w"]),
        safe_current_power_w=float(payload["safe_current_power_w"]),
        total_energy_kwh=float(payload["total_energy_kwh"]),
        safe_total_energy_kwh=float(payload["safe_total_energy_kwh"]),
        forecast_points=tuple(
            PvForecastPoint(
                timestamp=datetime.fromisoformat(str(point["timestamp"])),
                pv_power_w=float(point["pv_power_w"]),
                safe_pv_power_w=float(point["safe_pv_power_w"]),
            )
            for point in payload["forecast_points"]
        ),
    )
