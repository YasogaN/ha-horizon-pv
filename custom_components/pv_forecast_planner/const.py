"""Constants for PV Forecast Planner."""

from __future__ import annotations

DOMAIN = "pv_forecast_planner"

DEFAULT_NAME = "PV Forecast Planner"
DEFAULT_MODEL_DIR = "/config/pv_forecast_planner/models/default"
DEFAULT_PANEL_AZIMUTH_DEG = 350.0
DEFAULT_PANEL_TILT_DEG = 45.0
DEFAULT_FORECAST_DAYS = 2
DEFAULT_SAFE_FORECAST_FACTOR = 0.9
DEFAULT_SECONDARY_FORECAST_MODEL = "icon_eu"

CONF_FORECAST_DAYS = "forecast_days"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_MODEL_DIR = "model_dir"
CONF_PANEL_AZIMUTH_DEG = "panel_azimuth_deg"
CONF_PANEL_TILT_DEG = "panel_tilt_deg"
CONF_SECONDARY_FORECAST_MODEL = "secondary_forecast_model"
CONF_SAFE_FORECAST_FACTOR = "safe_forecast_factor"
CONF_TIMEZONE = "timezone"

SERVICE_UPDATE_FORECAST = "update_forecast"
SERVICE_UPDATE_LOAD_PLAN = "update_load_plan"
