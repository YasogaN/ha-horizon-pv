"""Physical solar feature helpers."""

from __future__ import annotations

from datetime import datetime
import math
from zoneinfo import ZoneInfo

CLEAR_SKY_BASE_IRRADIANCE_W_M2 = 1098.0
CLEAR_SKY_OPTICAL_DEPTH = 0.059
MAX_PANEL_IRRADIANCE_RATIO = 1.6


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value to the inclusive range."""
    return max(minimum, min(maximum, value))


def empty_physical_solar_features() -> dict[str, float]:
    """Return zeroed solar features for missing coordinates."""
    return {
        "solar_elevation_deg": 0.0,
        "solar_azimuth_deg": 0.0,
        "solar_zenith_deg": 90.0,
        "solar_incidence_angle_deg": 90.0,
        "solar_incidence_cos": 0.0,
        "clear_sky_horizontal_irradiance": 0.0,
        "clear_sky_panel_irradiance": 0.0,
    }


def solar_position(
    timestamp: datetime,
    latitude: float,
    longitude: float,
    timezone: str,
    panel_azimuth_deg: float,
    panel_tilt_deg: float,
) -> dict[str, float]:
    """Calculate simple solar-position and clear-sky panel features."""
    if latitude is None or longitude is None:
        return empty_physical_solar_features()

    aware_timestamp = timestamp.replace(tzinfo=ZoneInfo(timezone))
    utc_offset_hours = aware_timestamp.utcoffset().total_seconds() / 3600
    hour_float = timestamp.hour + timestamp.minute / 60
    day_of_year = timestamp.timetuple().tm_yday

    gamma = 2 * math.pi / 365 * (day_of_year - 1 + (hour_float - 12) / 24)
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )

    true_solar_minutes = (
        timestamp.hour * 60
        + timestamp.minute
        + equation_of_time
        + 4 * longitude
        - 60 * utc_offset_hours
    ) % 1440
    hour_angle = math.radians(true_solar_minutes / 4 - 180)
    latitude_rad = math.radians(latitude)

    cos_zenith = (
        math.sin(latitude_rad) * math.sin(declination)
        + math.cos(latitude_rad) * math.cos(declination) * math.cos(hour_angle)
    )
    cos_zenith = clamp(cos_zenith, -1.0, 1.0)
    zenith = math.degrees(math.acos(cos_zenith))
    elevation = 90 - zenith

    azimuth = (
        math.degrees(
            math.atan2(
                math.sin(hour_angle),
                math.cos(hour_angle) * math.sin(latitude_rad)
                - math.tan(declination) * math.cos(latitude_rad),
            )
        )
        + 180
    ) % 360

    elevation_rad = math.radians(elevation)
    azimuth_rad = math.radians(azimuth)
    panel_azimuth_rad = math.radians(panel_azimuth_deg)
    panel_tilt_rad = math.radians(panel_tilt_deg)

    sun_east = math.cos(elevation_rad) * math.sin(azimuth_rad)
    sun_north = math.cos(elevation_rad) * math.cos(azimuth_rad)
    sun_up = math.sin(elevation_rad)
    panel_east = math.sin(panel_azimuth_rad) * math.sin(panel_tilt_rad)
    panel_north = math.cos(panel_azimuth_rad) * math.sin(panel_tilt_rad)
    panel_up = math.cos(panel_tilt_rad)
    incidence_cos = clamp(
        sun_east * panel_east + sun_north * panel_north + sun_up * panel_up,
        0.0,
        1.0,
    )
    incidence_angle = math.degrees(math.acos(incidence_cos))

    if cos_zenith > 0 and elevation > 0:
        clear_sky_horizontal = (
            CLEAR_SKY_BASE_IRRADIANCE_W_M2
            * cos_zenith
            * math.exp(-CLEAR_SKY_OPTICAL_DEPTH / max(cos_zenith, 0.05))
        )
        panel_ratio = incidence_cos / max(cos_zenith, 0.05)
        clear_sky_panel = clear_sky_horizontal * clamp(
            panel_ratio,
            0.0,
            MAX_PANEL_IRRADIANCE_RATIO,
        )
    else:
        clear_sky_horizontal = 0.0
        clear_sky_panel = 0.0

    return {
        "solar_elevation_deg": elevation,
        "solar_azimuth_deg": azimuth,
        "solar_zenith_deg": zenith,
        "solar_incidence_angle_deg": incidence_angle,
        "solar_incidence_cos": incidence_cos,
        "clear_sky_horizontal_irradiance": clear_sky_horizontal,
        "clear_sky_panel_irradiance": clear_sky_panel,
    }
