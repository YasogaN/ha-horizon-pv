from __future__ import annotations

import json
import logging
from socket import timeout as SocketTimeout
import time
from time import perf_counter
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

_LOGGER = logging.getLogger(__name__)

OPEN_METEO_FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 90
REQUEST_RETRY_DELAYS_SECONDS = (5, 10, 20)
RETRY_HTTP_STATUS_CODES = {502, 503, 504}

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
    _LOGGER.debug("Fetching Open-Meteo data from %s", url)
    max_attempts = len(REQUEST_RETRY_DELAYS_SECONDS) + 1

    for attempt in range(1, max_attempts + 1):
        started = perf_counter()
        try:
            with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = response.read().decode("utf-8")
                status = getattr(response, "status", "unknown")

            _LOGGER.info(
                "Open-Meteo API response received: status=%s, bytes=%s, "
                "duration_s=%.2f, attempt=%s/%s",
                status,
                len(payload),
                perf_counter() - started,
                attempt,
                max_attempts,
            )
            return json.loads(payload)
        except HTTPError as err:
            if err.code not in RETRY_HTTP_STATUS_CODES or attempt >= max_attempts:
                _LOGGER.error(
                    "Open-Meteo API request failed permanently: status=%s, "
                    "attempts=%s, duration_s=%.2f",
                    err.code,
                    attempt,
                    perf_counter() - started,
                )
                raise
            retry_in = REQUEST_RETRY_DELAYS_SECONDS[attempt - 1]
            _LOGGER.warning(
                "Open-Meteo API request failed: status=%s, attempt=%s/%s, "
                "retry_in_s=%s",
                err.code,
                attempt,
                max_attempts,
                retry_in,
            )
            time.sleep(retry_in)
        except (TimeoutError, SocketTimeout, URLError) as err:
            if attempt >= max_attempts:
                _LOGGER.error(
                    "Open-Meteo API request failed permanently: error=%s, "
                    "attempts=%s, duration_s=%.2f",
                    err,
                    attempt,
                    perf_counter() - started,
                )
                raise
            retry_in = REQUEST_RETRY_DELAYS_SECONDS[attempt - 1]
            _LOGGER.warning(
                "Open-Meteo API request failed: error=%s, attempt=%s/%s, "
                "retry_in_s=%s",
                err,
                attempt,
                max_attempts,
                retry_in,
            )
            time.sleep(retry_in)

    raise RuntimeError("Open-Meteo API request failed")


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

    _LOGGER.info(
        "Fetching Open-Meteo forecast: lat=%s, lon=%s, timezone=%s, days=%s, model=%s",
        latitude,
        longitude,
        timezone,
        forecast_days,
        model or "default",
    )
    data = fetch_json(OPEN_METEO_FORECAST_ENDPOINT, params)
    rows = parse_minutely_15_forecast(data)
    first_timestamp = min(rows) if rows else None
    last_timestamp = max(rows) if rows else None
    sample = rows.get(first_timestamp, {}) if first_timestamp is not None else {}
    _LOGGER.info(
        "Open-Meteo forecast loaded: model=%s, rows=%s, first=%s, last=%s, "
        "sample_shortwave=%s, sample_cloud_cover=%s",
        model or "default",
        len(rows),
        first_timestamp,
        last_timestamp,
        sample.get("shortwave_radiation"),
        sample.get("cloud_cover"),
    )
    return rows


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
