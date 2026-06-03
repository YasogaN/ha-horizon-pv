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

        config = PvForecastConfig(
            model_dir=self.entry.data[CONF_MODEL_DIR],
            latitude=float(self.entry.data[CONF_LATITUDE]),
            longitude=float(self.entry.data[CONF_LONGITUDE]),
            timezone=str(self.entry.data[CONF_TIMEZONE]),
            panel_azimuth_deg=float(self.entry.data[CONF_PANEL_AZIMUTH_DEG]),
            panel_tilt_deg=float(self.entry.data[CONF_PANEL_TILT_DEG]),
            forecast_days=int(self.entry.data[CONF_FORECAST_DAYS]),
            secondary_forecast_model=str(self.entry.data[CONF_SECONDARY_FORECAST_MODEL]),
        )
        try:
            return await self.hass.async_add_executor_job(
                partial(create_pv_forecast, config, now=dt_util.now()),
            )
        except Exception as err:
            raise UpdateFailed(f"Could not update PV forecast: {err}") from err
