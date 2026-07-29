from __future__ import annotations

from datetime import datetime
import math
from typing import Any

try:
    from .physical_model import clamp, solar_position
except ImportError:
    from physical_model import clamp, solar_position

FEATURE_COLUMNS = [
    "clear_sky_panel_irradiance",
    "cloud_cover",
    "solar_elevation_deg",
    "hour_sin",
    "hour_cos",
    "shortwave_radiation",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
]


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_feature_rows(
    weather: dict[datetime, dict[str, float]],
    *,
    observed_peak_w: float,
    latitude: float,
    longitude: float,
    timezone: str,
    panel_azimuth_deg: float,
    panel_tilt_deg: float,
) -> list[dict[str, Any]]:
    timestamps = sorted(weather.keys())
    if not timestamps:
        raise ValueError("No weather data available")

    rows: list[dict[str, Any]] = []
    for timestamp in timestamps:
        w = weather[timestamp]
        hour_float = timestamp.hour + timestamp.minute / 60
        solar = solar_position(
            timestamp,
            latitude,
            longitude,
            timezone,
            panel_azimuth_deg,
            panel_tilt_deg,
        )
        rows.append({
            "_timestamp": timestamp,
            "clear_sky_panel_irradiance": safe_float(
                solar.get("clear_sky_panel_irradiance")
            ),
            "cloud_cover": safe_float(w.get("cloud_cover")),
            "solar_elevation_deg": safe_float(solar.get("solar_elevation_deg")),
            "hour_sin": math.sin(2 * math.pi * hour_float / 24),
            "hour_cos": math.cos(2 * math.pi * hour_float / 24),
            "shortwave_radiation": safe_float(w.get("shortwave_radiation")),
            "temperature_2m": safe_float(w.get("temperature_2m")),
            "relative_humidity_2m": safe_float(w.get("relative_humidity_2m")),
            "wind_speed_10m": safe_float(w.get("wind_speed_10m")),
            "cloud_cover_low": safe_float(w.get("cloud_cover_low")),
            "cloud_cover_mid": safe_float(w.get("cloud_cover_mid")),
            "cloud_cover_high": safe_float(w.get("cloud_cover_high")),
        })

    return rows


def build_feature_matrix(
    rows: list[dict[str, Any]],
    feature_columns: list[str],
) -> list[list[float]]:
    return [
        [safe_float(row[col]) for col in feature_columns]
        for row in rows
    ]
