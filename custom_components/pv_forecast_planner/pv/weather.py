from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import urlopen

OPEN_METEO_FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 90

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


def fetch_json(endpoint: str, params: dict[str, object]) -> dict:
    """Fetch JSON from an HTTP endpoint."""
    url = endpoint + "?" + urlencode(params)
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = response.read().decode("utf-8")

    return json.loads(payload)


def fetch_open_meteo_forecast(
    latitude: float,
    longitude: float,
    timezone: str,
    forecast_days: int,
    model: str | None = None,
) -> dict[datetime, dict[str, float]]:
    """Fetch 15-minute current forecast data from Open-Meteo."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "forecast_days": forecast_days,
        "minutely_15": ",".join(WEATHER_15_MIN_VARIABLES),
    }
    if model is not None:
        params["models"] = model

    data = fetch_json(OPEN_METEO_FORECAST_ENDPOINT, params)
    return parse_minutely_15_forecast(data)


def parse_minutely_15_forecast(data: dict) -> dict[datetime, dict[str, float]]:
    """Parse Open-Meteo minutely_15 data into timestamp-indexed rows."""
    block = data.get("minutely_15")
    if not block or "time" not in block:
        raise ValueError("Open-Meteo response does not contain minutely_15 data")

    rows: dict[datetime, dict[str, float]] = {}

    for index, timestamp_text in enumerate(block["time"]):
        timestamp = datetime.fromisoformat(timestamp_text)
        row = {}

        for variable in WEATHER_15_MIN_VARIABLES:
            values = block.get(variable, [])
            value = values[index] if index < len(values) else None
            row[variable] = 0.0 if value is None else float(value)

        rows[timestamp] = row

    return rows
