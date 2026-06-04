"""Data coordinator for PV Forecast Planner."""

from __future__ import annotations

from datetime import datetime
from functools import partial
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    from .pv.forecast import PvForecastResult

_LOGGER = logging.getLogger(__name__)
CACHE_DIR_NAME = "pv_forecast_planner"


class PvForecastCoordinator(DataUpdateCoordinator):
    """Coordinate PV forecast refreshes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.cache_path = Path(
            hass.config.path(CACHE_DIR_NAME, f"last_forecast_{entry.entry_id}.json")
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )

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
        _LOGGER.info(
            "Loaded cached PV forecast: path=%s, generated_at=%s, points=%s",
            self.cache_path,
            result.generated_at,
            len(result.forecast_points),
        )

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
