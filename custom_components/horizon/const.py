from __future__ import annotations

DOMAIN = "horizon"

DEFAULT_NAME = "Horizon"
DEFAULT_PANEL_AZIMUTH_DEG = 180.0
DEFAULT_PANEL_TILT_DEG = 35.0
DEFAULT_FORECAST_DAYS = 2
DEFAULT_BOOTSTRAP_DAYS = 7
DEFAULT_LEARNING_RATE = 0.01
DEFAULT_COLD_START_CLOUD_FACTOR = 0.6

CONF_PV_SENSOR_ENTITY = "pv_sensor_entity"
CONF_PV_ENERGY_SENSOR_ENTITY = "pv_energy_sensor_entity"
CONF_BOOTSTRAP_DAYS = "bootstrap_days"
CONF_INITIAL_PEAK_POWER_W = "initial_peak_power_w"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_TIMEZONE = "timezone"
CONF_PANEL_AZIMUTH_DEG = "panel_azimuth_deg"
CONF_PANEL_TILT_DEG = "panel_tilt_deg"
CONF_FORECAST_DAYS = "forecast_days"

SERVICE_UPDATE_FORECAST = "update_forecast"
SERVICE_LEARN = "learn"
SERVICE_BOOTSTRAP = "bootstrap"
SERVICE_GET_STATE = "get_state"
