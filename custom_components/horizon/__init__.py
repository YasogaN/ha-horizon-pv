from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_BOOTSTRAP_DAYS,
    DOMAIN,
    SERVICE_BOOTSTRAP,
    SERVICE_GET_STATE,
    SERVICE_LEARN,
    SERVICE_UPDATE_FORECAST,
)

PLATFORMS: list[Platform] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import HorizonCoordinator

    _LOGGER.info("Setting up Horizon entry %s", entry.entry_id)
    coordinator = HorizonCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    coordinator.load_state()
    await coordinator.async_load_cached_data()
    coordinator.async_start_current_value_refresh()
    entry.async_on_unload(coordinator.async_stop_current_value_refresh)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_update_forecast(call: ServiceCall) -> None:
        for item in hass.data.get(DOMAIN, {}).values():
            await item.async_request_refresh()

    async def handle_learn(call: ServiceCall) -> None:
        for item in hass.data.get(DOMAIN, {}).values():
            await item.async_learn()

    async def handle_bootstrap(call: ServiceCall) -> None:
        days = call.data.get("days")
        for item in hass.data.get(DOMAIN, {}).values():
            await item.async_bootstrap(days=days)

    async def handle_get_state(call: ServiceCall) -> dict:
        from homeassistant.core import ServiceResponse
        results = {}
        for entry_id, item in hass.data.get(DOMAIN, {}).items():
            results[entry_id] = item.get_state()
        return results

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_FORECAST):
        hass.services.async_register(
            DOMAIN, SERVICE_UPDATE_FORECAST, handle_update_forecast,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_LEARN):
        hass.services.async_register(
            DOMAIN, SERVICE_LEARN, handle_learn,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_BOOTSTRAP):
        hass.services.async_register(
            DOMAIN, SERVICE_BOOTSTRAP, handle_bootstrap,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_STATE):
        hass.services.async_register(
            DOMAIN, SERVICE_GET_STATE, handle_get_state,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            for service in [
                SERVICE_UPDATE_FORECAST,
                SERVICE_LEARN,
                SERVICE_BOOTSTRAP,
                SERVICE_GET_STATE,
            ]:
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
