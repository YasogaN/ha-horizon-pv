from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_BOOTSTRAP_DAYS,
    CONF_FORECAST_DAYS,
    CONF_INITIAL_PEAK_POWER_W,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PANEL_AZIMUTH_DEG,
    CONF_PANEL_TILT_DEG,
    CONF_PV_ENERGY_SENSOR_ENTITY,
    CONF_PV_SENSOR_ENTITY,
    CONF_TIMEZONE,
    DEFAULT_BOOTSTRAP_DAYS,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_NAME,
    DEFAULT_PANEL_AZIMUTH_DEG,
    DEFAULT_PANEL_TILT_DEG,
    DOMAIN,
)


class HorizonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return HorizonOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, object] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=str(user_input[CONF_NAME]),
                data=user_input,
            )

        defaults = {
            CONF_NAME: DEFAULT_NAME,
            CONF_PV_SENSOR_ENTITY: "",
            CONF_PV_ENERGY_SENSOR_ENTITY: "",
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_TIMEZONE: self.hass.config.time_zone,
            CONF_PANEL_AZIMUTH_DEG: DEFAULT_PANEL_AZIMUTH_DEG,
            CONF_PANEL_TILT_DEG: DEFAULT_PANEL_TILT_DEG,
            CONF_INITIAL_PEAK_POWER_W: "",
            CONF_BOOTSTRAP_DAYS: DEFAULT_BOOTSTRAP_DAYS,
            CONF_FORECAST_DAYS: DEFAULT_FORECAST_DAYS,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(defaults, include_name=True),
            errors=errors,
        )


class HorizonOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, object] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = dict(self._config_entry.data)
        defaults.update(self._config_entry.options)
        defaults.setdefault(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS)

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(defaults, include_name=False),
        )


def _schema(defaults: dict[str, object], *, include_name: bool) -> vol.Schema:
    fields: dict[vol.Marker, object] = {}
    if include_name:
        fields[vol.Required(CONF_NAME, default=defaults[CONF_NAME])] = str

    fields.update({
        vol.Required(
            CONF_PV_SENSOR_ENTITY,
            default=defaults.get(CONF_PV_SENSOR_ENTITY, ""),
        ): cv.entity_id,
        vol.Optional(
            CONF_PV_ENERGY_SENSOR_ENTITY,
            default=defaults.get(CONF_PV_ENERGY_SENSOR_ENTITY, ""),
        ): cv.entity_id,
        vol.Required(
            CONF_LATITUDE,
            default=defaults[CONF_LATITUDE],
        ): vol.Coerce(float),
        vol.Required(
            CONF_LONGITUDE,
            default=defaults[CONF_LONGITUDE],
        ): vol.Coerce(float),
        vol.Required(
            CONF_TIMEZONE,
            default=defaults[CONF_TIMEZONE],
        ): str,
        vol.Required(
            CONF_PANEL_AZIMUTH_DEG,
            default=defaults[CONF_PANEL_AZIMUTH_DEG],
        ): vol.Coerce(float),
        vol.Required(
            CONF_PANEL_TILT_DEG,
            default=defaults[CONF_PANEL_TILT_DEG],
        ): vol.Coerce(float),
        vol.Optional(
            CONF_INITIAL_PEAK_POWER_W,
            default=defaults.get(CONF_INITIAL_PEAK_POWER_W, ""),
        ): str,
        vol.Required(
            CONF_FORECAST_DAYS,
            default=defaults.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    })
    if include_name:
        fields[vol.Optional(
            CONF_BOOTSTRAP_DAYS,
            default=defaults.get(CONF_BOOTSTRAP_DAYS, DEFAULT_BOOTSTRAP_DAYS),
        )] = vol.All(vol.Coerce(int), vol.Range(min=0, max=90))

    return vol.Schema(fields)
