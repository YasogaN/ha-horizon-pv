"""Config flow for PV Forecast Planner."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult

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

    async def async_step_user(
        self,
        user_input: dict[str, object] | None = None,
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=str(user_input[CONF_NAME]),
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_MODEL_DIR, default=DEFAULT_MODEL_DIR): str,
                vol.Required(
                    CONF_LATITUDE,
                    default=self.hass.config.latitude,
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LONGITUDE,
                    default=self.hass.config.longitude,
                ): vol.Coerce(float),
                vol.Required(
                    CONF_TIMEZONE,
                    default=self.hass.config.time_zone,
                ): str,
                vol.Required(
                    CONF_PANEL_AZIMUTH_DEG,
                    default=DEFAULT_PANEL_AZIMUTH_DEG,
                ): vol.Coerce(float),
                vol.Required(
                    CONF_PANEL_TILT_DEG,
                    default=DEFAULT_PANEL_TILT_DEG,
                ): vol.Coerce(float),
                vol.Required(
                    CONF_FORECAST_DAYS,
                    default=DEFAULT_FORECAST_DAYS,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
                vol.Required(
                    CONF_SECONDARY_FORECAST_MODEL,
                    default=DEFAULT_SECONDARY_FORECAST_MODEL,
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
