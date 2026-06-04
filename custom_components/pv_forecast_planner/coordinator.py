"""Data coordinator for PV Forecast Planner."""

from __future__ import annotations

from functools import partial
import logging
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
    CONF_TIMEZONE,
    DOMAIN,
)

if TYPE_CHECKING:
    from .pv.forecast import PvForecastResult

_LOGGER = logging.getLogger(__name__)


class PvForecastCoordinator(DataUpdateCoordinator):
    """Coordinate PV forecast refreshes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
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
            secondary_forecast_model=str(settings[CONF_SECONDARY_FORECAST_MODEL]),
        )
        _LOGGER.info(
            "Starting PV forecast update: model_dir=%s, lat=%s, lon=%s, timezone=%s, "
            "forecast_days=%s, secondary_model=%s",
            config.model_dir,
            config.latitude,
            config.longitude,
            config.timezone,
            config.forecast_days,
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
            return result
        except Exception as err:
            _LOGGER.exception("PV forecast update failed")
            raise UpdateFailed(f"Could not update PV forecast: {err}") from err
