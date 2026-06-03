"""Feature construction for PV forecast inference."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any

try:
    from .physical_model import clamp, solar_position
except ImportError:
    from physical_model import clamp, solar_position

MAX_CLEAR_SKY_INDEX = 2.0
MAX_CLEAR_SKY_POWER_FACTOR = 1.15


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float, falling back to a default."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def time_features(timestamp: datetime) -> dict[str, Any]:
    """Build time-based features matching the training dataset."""
    hour_float = timestamp.hour + timestamp.minute / 60
    day_of_year = timestamp.timetuple().tm_yday
    return {
        "_timestamp": timestamp,
        "timestamp": timestamp.isoformat(sep=" "),
        "date": timestamp.date().isoformat(),
        "time": timestamp.time().isoformat(timespec="minutes"),
        "hour": timestamp.hour,
        "minute": timestamp.minute,
        "day_of_week": timestamp.weekday(),
        "month": timestamp.month,
        "day_of_year": day_of_year,
        "hour_sin": math.sin(2 * math.pi * hour_float / 24),
        "hour_cos": math.cos(2 * math.pi * hour_float / 24),
        "day_of_year_sin": math.sin(2 * math.pi * day_of_year / 366),
        "day_of_year_cos": math.cos(2 * math.pi * day_of_year / 366),
    }


def prefix_weather_row(row: dict[str, float], prefix: str) -> dict[str, float]:
    """Prefix raw Open-Meteo variables with forecast or icon."""
    return {f"{prefix}_{column}": safe_float(value) for column, value in row.items()}


def physical_features(
    solar_features: dict[str, float],
    forecast_row: dict[str, float],
    secondary_forecast_row: dict[str, float],
    observed_peak_w: float,
) -> dict[str, float]:
    """Build physical features matching the training dataset."""
    features = dict(solar_features)
    clear_sky_horizontal = features["clear_sky_horizontal_irradiance"]
    clear_sky_panel = features["clear_sky_panel_irradiance"]
    forecast_shortwave = safe_float(forecast_row.get("forecast_shortwave_radiation"))
    icon_shortwave = safe_float(secondary_forecast_row.get("icon_shortwave_radiation"))
    forecast_panel = safe_float(forecast_row.get("forecast_global_tilted_irradiance"))
    icon_panel = safe_float(secondary_forecast_row.get("icon_global_tilted_irradiance"))

    features.update(
        {
            "forecast_clear_sky_index": (
                clamp(forecast_shortwave / clear_sky_horizontal, 0.0, MAX_CLEAR_SKY_INDEX)
                if clear_sky_horizontal > 1
                else 0.0
            ),
            "icon_clear_sky_index": (
                clamp(icon_shortwave / clear_sky_horizontal, 0.0, MAX_CLEAR_SKY_INDEX)
                if clear_sky_horizontal > 1
                else 0.0
            ),
            "forecast_panel_irradiance_ratio": (
                clamp(forecast_panel / clear_sky_panel, 0.0, MAX_CLEAR_SKY_INDEX)
                if clear_sky_panel > 1
                else 0.0
            ),
            "icon_panel_irradiance_ratio": (
                clamp(icon_panel / clear_sky_panel, 0.0, MAX_CLEAR_SKY_INDEX)
                if clear_sky_panel > 1
                else 0.0
            ),
            "pv_observed_peak_w": observed_peak_w,
            "pv_clear_sky_power_estimate_w": observed_peak_w
            * clamp(clear_sky_panel / 1000.0, 0.0, MAX_CLEAR_SKY_POWER_FACTOR),
        }
    )
    return features


def build_feature_rows(
    primary_weather: dict[datetime, dict[str, float]],
    secondary_weather: dict[datetime, dict[str, float]],
    *,
    observed_peak_w: float,
    latitude: float,
    longitude: float,
    timezone: str,
    panel_azimuth_deg: float,
    panel_tilt_deg: float,
) -> list[dict[str, Any]]:
    """Build base feature rows from primary and secondary forecast data."""
    timestamps = sorted(set(primary_weather) & set(secondary_weather))
    if not timestamps:
        raise ValueError("No common timestamps in Open-Meteo forecasts")

    rows: list[dict[str, Any]] = []
    for timestamp in timestamps:
        forecast_row = prefix_weather_row(primary_weather[timestamp], "forecast")
        icon_row = prefix_weather_row(secondary_weather[timestamp], "icon")
        solar_features = solar_position(
            timestamp,
            latitude,
            longitude,
            timezone,
            panel_azimuth_deg,
            panel_tilt_deg,
        )
        rows.append(
            {
                **time_features(timestamp),
                **physical_features(
                    solar_features,
                    forecast_row,
                    icon_row,
                    observed_peak_w,
                ),
                **forecast_row,
                **icon_row,
            }
        )

    return rows


def value_at(rows: list[dict[str, Any]], index: int, column: str) -> float:
    """Read a numeric column with clamped row indexing."""
    index = min(max(index, 0), len(rows) - 1)
    return safe_float(rows[index][column])


def feature_value(rows: list[dict[str, Any]], index: int, feature_name: str) -> float:
    """Read direct, neighboring, or delta feature values."""
    row = rows[index]
    if feature_name in row:
        return safe_float(row[feature_name])

    for suffix, offset in (
        ("_delta_prev_1", None),
        ("_delta_next_1", None),
        ("_prev_4", -4),
        ("_prev_2", -2),
        ("_prev_1", -1),
        ("_next_4", 4),
        ("_next_2", 2),
        ("_next_1", 1),
    ):
        if feature_name.endswith(suffix):
            base_column = feature_name[: -len(suffix)]
            if suffix == "_delta_prev_1":
                return value_at(rows, index, base_column) - value_at(rows, index - 1, base_column)
            if suffix == "_delta_next_1":
                return value_at(rows, index + 1, base_column) - value_at(rows, index, base_column)
            return value_at(rows, index + offset, base_column)

    raise KeyError(f"Feature missing in forecast data: {feature_name}")


def build_feature_matrix(
    rows: list[dict[str, Any]],
    feature_columns: list[str],
) -> list[list[float]]:
    """Build an XGBoost feature matrix in the trained feature order."""
    return [
        [feature_value(rows, index, column) for column in feature_columns]
        for index in range(len(rows))
    ]
