#!/usr/bin/env python3
"""Zentrale Einstellungen fuer das PV-Forecast-Projekt."""

from datetime import datetime
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_dotenv(path):
    """Laedt einfache KEY=VALUE Eintraege aus .env ohne externe Abhaengigkeit."""
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def env_str(name, default=""):
    return os.environ.get(name, default)


def env_path(name, default):
    value = env_str(name)
    if not value:
        return default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path


def env_float(name, default=None):
    value = env_str(name)
    if value == "":
        return default
    return float(value)


def env_int(name, default):
    value = env_str(name)
    if value == "":
        return default
    return int(value)


def env_int_list(name, default):
    value = env_str(name)
    if value == "":
        return default
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def env_date(name, default):
    value = env_str(name)
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d")


load_dotenv(PROJECT_DIR / ".env")

DATA_DIR = env_path("DATA_DIR", PROJECT_DIR / "data")
ENERGY_BALANCE_DIR = env_path("ENERGY_BALANCE_DIR", DATA_DIR / "energy_balance")

# Inklusive Start- und Enddatum.
START_DATE = env_date("START_DATE", datetime(2024, 8, 1))
END_DATE = env_date("END_DATE", datetime(2026, 5, 24))
ML_START_DATE = env_date("ML_START_DATE", START_DATE)
ML_END_DATE = env_date("ML_END_DATE", END_DATE)

TIMEZONE = env_str("TIMEZONE", "Europe/Vienna")

SUNNYPORTAL_EMAIL = env_str("SUNNYPORTAL_EMAIL")
SUNNYPORTAL_PASSWORD = env_str("SUNNYPORTAL_PASSWORD")
SUNNYPORTAL_LOGIN_URL = env_str(
    "SUNNYPORTAL_LOGIN_URL",
    "https://www.sunnyportal.com/FixedPages/HoManEnergyRedesign.aspx",
)

# Wichtig fuer Wetterdaten. Bitte mit den Koordinaten der PV-Anlage befuellen.
# Beispiel Wien waere LATITUDE = 48.2082, LONGITUDE = 16.3738.
LOCATION_NAME = env_str("LOCATION_NAME")
LATITUDE = env_float("LATITUDE")
LONGITUDE = env_float("LONGITUDE")
ELEVATION = env_float("ELEVATION")
PV_PANEL_AZIMUTH_DEG = env_float("PV_PANEL_AZIMUTH_DEG", 350.0)
PV_PANEL_TILT_DEG = env_float("PV_PANEL_TILT_DEG", 45.0)
PV_OBSERVED_PEAK_W = env_float("PV_OBSERVED_PEAK_W")

ML_DATA_DIR = env_path("ML_DATA_DIR", DATA_DIR / "ml")
ML_FEATURES_DIR = env_path("ML_FEATURES_DIR", ML_DATA_DIR / "features")

WEATHER_FORECAST_OUTPUT = env_path("WEATHER_FORECAST_OUTPUT", ML_FEATURES_DIR / "weather_forecast_features.csv")
WEATHER_SECONDARY_FORECAST_OUTPUT = env_path(
    "WEATHER_SECONDARY_FORECAST_OUTPUT",
    ML_FEATURES_DIR / "weather_forecast_icon_features.csv",
)
WEATHER_SECONDARY_FORECAST_MODEL = env_str("WEATHER_SECONDARY_FORECAST_MODEL", "icon_eu")
WEATHER_OBSERVED_OUTPUT = env_path("WEATHER_OBSERVED_OUTPUT", ML_FEATURES_DIR / "weather_observed_features.csv")
ML_DATASET_OUTPUT = env_path("ML_DATASET_OUTPUT", ML_DATA_DIR / "ml_pv_forecast_dataset.csv")
MODEL_DIR = env_path("MODEL_DIR", PROJECT_DIR / "models" / "pv_forecast_xgboost")

WEATHER_FORECAST_ENDPOINT = "https://historical-forecast-api.open-meteo.com/v1/forecast"
WEATHER_OBSERVED_ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"

XGB_OBJECTIVE = env_str("XGB_OBJECTIVE", "reg:squarederror")
XGB_N_ESTIMATORS = env_int("XGB_N_ESTIMATORS", 2000)
XGB_MAX_DEPTH = env_int("XGB_MAX_DEPTH", 9)
XGB_LEARNING_RATE = env_float("XGB_LEARNING_RATE", 0.04)
XGB_SUBSAMPLE = env_float("XGB_SUBSAMPLE", 0.9)
XGB_COLSAMPLE_BYTREE = env_float("XGB_COLSAMPLE_BYTREE", 0.85)
XGB_MIN_CHILD_WEIGHT = env_float("XGB_MIN_CHILD_WEIGHT", 1.0)
XGB_REG_LAMBDA = env_float("XGB_REG_LAMBDA", 1.5)
XGB_RANDOM_STATE = env_int("XGB_RANDOM_STATE", 42)
XGB_N_JOBS = env_int("XGB_N_JOBS", -1)

USE_NEIGHBOR_FEATURES = env_str("USE_NEIGHBOR_FEATURES", "true").lower() == "true"
USE_NEIGHBOR_DELTAS = env_str("USE_NEIGHBOR_DELTAS", "true").lower() == "true"
NEIGHBOR_OFFSETS = env_int_list("NEIGHBOR_OFFSETS", (-4, -2, -1, 1, 2, 4))
ACTIVE_PV_THRESHOLD_W = env_float("ACTIVE_PV_THRESHOLD_W", 200.0)
SAFE_PREDICTION_FACTOR = env_float("SAFE_PREDICTION_FACTOR", 0.90)
SAVE_FEATURE_IMPORTANCE = env_str("SAVE_FEATURE_IMPORTANCE", "true").lower() == "true"

# Historische Forecast-Daten: entspricht moeglichst den Daten, die ein
# Vorhersagemodell fuer spaetere Live-Optimierung auch sehen wuerde.
WEATHER_15_MIN_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "snowfall",
    "snow_depth",
    "weather_code",
    "pressure_msl",
    "surface_pressure",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "vapour_pressure_deficit",
    "et0_fao_evapotranspiration",
    "wind_speed_10m",
    "wind_speed_80m",
    "wind_speed_120m",
    "wind_speed_180m",
    "wind_direction_10m",
    "wind_direction_80m",
    "wind_direction_120m",
    "wind_direction_180m",
    "wind_gusts_10m",
    "visibility",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "direct_normal_irradiance",
    "global_tilted_irradiance",
    "terrestrial_radiation",
    "is_day",
    "sunshine_duration",
]

# Tatsaechliche historische Wetterwerte/Reanalyse. Diese sind stuendlich und
# eignen sich als Realitaetscheck oder Zusatzfeatures, aber nicht als Ersatz
# fuer historische Forecast-Daten beim Training.
WEATHER_HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "rain",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "is_day",
    "sunshine_duration",
]
