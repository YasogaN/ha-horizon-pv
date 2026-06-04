"""PV Forecast Planner integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, SERVICE_UPDATE_FORECAST, SERVICE_UPDATE_LOAD_PLAN

PLATFORMS: list[Platform] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PV Forecast Planner from a config entry."""
    from .coordinator import PvForecastCoordinator

    _LOGGER.info("Setting up PV Forecast Planner entry %s", entry.entry_id)
    coordinator = PvForecastCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_load_cached_data()
    coordinator.async_start_current_value_refresh()
    entry.async_on_unload(coordinator.async_stop_current_value_refresh)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_FORECAST):

        async def handle_update_forecast(call: ServiceCall) -> None:
            """Refresh all configured PV forecast coordinators."""
            _LOGGER.info("PV forecast update service called")
            for item in hass.data.get(DOMAIN, {}).values():
                await item.async_request_refresh()
                _LOGGER.info(
                    "PV forecast update finished, success=%s",
                    item.last_update_success,
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_FORECAST,
            handle_update_forecast,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_LOAD_PLAN):

        async def handle_update_load_plan(call: ServiceCall) -> None:
            """Refresh load plans for all configured coordinators."""
            _LOGGER.info("Load plan update service called")
            for item in hass.data.get(DOMAIN, {}).values():
                await item.async_update_load_plan()
                _LOGGER.info("Load plan update finished")

        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_LOAD_PLAN,
            handle_update_load_plan,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            if hass.services.has_service(DOMAIN, SERVICE_UPDATE_FORECAST):
                hass.services.async_remove(DOMAIN, SERVICE_UPDATE_FORECAST)
            if hass.services.has_service(DOMAIN, SERVICE_UPDATE_LOAD_PLAN):
                hass.services.async_remove(DOMAIN, SERVICE_UPDATE_LOAD_PLAN)
    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
