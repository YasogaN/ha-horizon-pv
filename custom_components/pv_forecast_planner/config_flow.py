"""Config flow for PV Forecast Planner."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.config_entries import ConfigFlowResult

from .const import (
    CONF_FORECAST_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODEL_DIR,
    CONF_PANEL_AZIMUTH_DEG,
    CONF_PANEL_TILT_DEG,
    CONF_SECONDARY_FORECAST_MODEL,
    CONF_TIMEZONE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_MODEL_DIR,
    DEFAULT_NAME,
    DEFAULT_PANEL_AZIMUTH_DEG,
    DEFAULT_PANEL_TILT_DEG,
    DEFAULT_SECONDARY_FORECAST_MODEL,
    DOMAIN,
)


class PvForecastPlannerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PV Forecast Planner."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return PvForecastPlannerOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, object] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step."""
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
            CONF_MODEL_DIR: DEFAULT_MODEL_DIR,
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_TIMEZONE: self.hass.config.time_zone,
            CONF_PANEL_AZIMUTH_DEG: DEFAULT_PANEL_AZIMUTH_DEG,
            CONF_PANEL_TILT_DEG: DEFAULT_PANEL_TILT_DEG,
            CONF_FORECAST_DAYS: DEFAULT_FORECAST_DAYS,
            CONF_SECONDARY_FORECAST_MODEL: DEFAULT_SECONDARY_FORECAST_MODEL,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(defaults, include_name=True),
            errors=errors,
        )


class PvForecastPlannerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for PV Forecast Planner."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, object] | None = None,
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = dict(self.config_entry.data)
        defaults.update(self.config_entry.options)

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(defaults, include_name=False),
        )


def _schema(defaults: dict[str, object], *, include_name: bool) -> vol.Schema:
    """Build the setup/options schema."""
    fields: dict[vol.Marker, object] = {}
    if include_name:
        fields[vol.Required(CONF_NAME, default=defaults[CONF_NAME])] = str

    fields.update(
        {
            vol.Required(CONF_MODEL_DIR, default=defaults[CONF_MODEL_DIR]): str,
            vol.Required(CONF_LATITUDE, default=defaults[CONF_LATITUDE]): vol.Coerce(
                float
            ),
            vol.Required(CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]): vol.Coerce(
                float
            ),
            vol.Required(CONF_TIMEZONE, default=defaults[CONF_TIMEZONE]): str,
            vol.Required(
                CONF_PANEL_AZIMUTH_DEG,
                default=defaults[CONF_PANEL_AZIMUTH_DEG],
            ): vol.Coerce(float),
            vol.Required(
                CONF_PANEL_TILT_DEG,
                default=defaults[CONF_PANEL_TILT_DEG],
            ): vol.Coerce(float),
            vol.Required(
                CONF_FORECAST_DAYS,
                default=defaults[CONF_FORECAST_DAYS],
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
            vol.Required(
                CONF_SECONDARY_FORECAST_MODEL,
                default=defaults[CONF_SECONDARY_FORECAST_MODEL],
            ): str,
        }
    )
    return vol.Schema(fields)
