#!/usr/bin/env python3
"""Laedt Wetter-Forecast- und Messdaten passend zum PV-Zeitraum."""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    DATA_DIR,
    END_DATE,
    LATITUDE,
    LOCATION_NAME,
    LONGITUDE,
    TIMEZONE,
    START_DATE,
    WEATHER_15_MIN_VARIABLES,
    WEATHER_FORECAST_ENDPOINT,
    WEATHER_FORECAST_OUTPUT,
    WEATHER_HOURLY_VARIABLES,
    WEATHER_OBSERVED_ENDPOINT,
    WEATHER_OBSERVED_OUTPUT,
    WEATHER_SECONDARY_FORECAST_MODEL,
    WEATHER_SECONDARY_FORECAST_OUTPUT,
)

REQUEST_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 10


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d")


def date_arg(value):
    try:
        return parse_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Datum muss im Format YYYY-MM-DD sein") from exc


def require_coordinate(value, name):
    if value is None:
        raise SystemExit(
            f"{name} fehlt. Bitte in config/settings.py setzen oder per CLI uebergeben."
        )
    return float(value)


def fetch_json(endpoint, params):
    url = endpoint + "?" + urlencode(params)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"API-Aufruf ({attempt}/{MAX_ATTEMPTS}): {url}")
            with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP-Fehler {exc.code}: {body[:1000]}")
            if attempt == MAX_ATTEMPTS:
                raise
        except (URLError, TimeoutError) as exc:
            print(f"Netzwerkfehler: {exc}")
            if attempt == MAX_ATTEMPTS:
                raise

        print(f"Warte {RETRY_SLEEP_SECONDS}s und versuche es erneut...")
        time.sleep(RETRY_SLEEP_SECONDS)

    raise RuntimeError("API-Aufruf fehlgeschlagen")


def write_timeseries_csv(data, block_name, variables, output_path, source_label):
    block = data.get(block_name)
    if not block or "time" not in block:
        raise RuntimeError(f"API-Antwort enthaelt keinen Block {block_name!r}")

    times = block["time"]
    units = data.get(f"{block_name}_units", {})
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "timestamp",
        "date",
        "time",
        "source",
        "latitude",
        "longitude",
        "elevation",
        "timezone",
        *variables,
    ]

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for index, timestamp_text in enumerate(times):
            timestamp = datetime.fromisoformat(timestamp_text)
            row = {
                "timestamp": timestamp.isoformat(sep=" "),
                "date": timestamp.date().isoformat(),
                "time": timestamp.time().isoformat(timespec="minutes"),
                "source": source_label,
                "latitude": data.get("latitude", ""),
                "longitude": data.get("longitude", ""),
                "elevation": data.get("elevation", ""),
                "timezone": data.get("timezone", ""),
            }
            for variable in variables:
                values = block.get(variable, [])
                row[variable] = values[index] if index < len(values) else ""
            writer.writerow(row)

    print(f"Geschrieben: {output_path}")
    print(f"Zeilen: {len(times)}")
    if units:
        print("Einheiten:")
        for variable in variables:
            print(f"  {variable}: {units.get(variable, '')}")


def fetch_historical_forecast(
    start_date,
    end_date,
    latitude,
    longitude,
    timezone,
    output_path,
    model=None,
    source_label="open_meteo_historical_forecast_15min",
):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "timezone": timezone,
        "minutely_15": ",".join(WEATHER_15_MIN_VARIABLES),
    }
    if model:
        params["models"] = model
    data = fetch_json(WEATHER_FORECAST_ENDPOINT, params)
    write_timeseries_csv(
        data,
        "minutely_15",
        WEATHER_15_MIN_VARIABLES,
        output_path,
        source_label,
    )


def fetch_observed_weather(start_date, end_date, latitude, longitude, timezone, output_path):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "timezone": timezone,
        "hourly": ",".join(WEATHER_HOURLY_VARIABLES),
    }
    data = fetch_json(WEATHER_OBSERVED_ENDPOINT, params)
    write_timeseries_csv(
        data,
        "hourly",
        WEATHER_HOURLY_VARIABLES,
        output_path,
        "open_meteo_historical_weather_hourly",
    )


def scrape_weather(
    start_date,
    end_date,
    latitude,
    longitude,
    timezone,
    forecast_output,
    secondary_forecast_output,
    secondary_forecast_model,
    observed_output,
    skip_forecast=False,
    skip_secondary_forecast=False,
    skip_observed=False,
):
    print("Wetterdaten-Scraper")
    if LOCATION_NAME:
        print(f"Ort: {LOCATION_NAME}")
    print(f"Zeitraum: {start_date:%d.%m.%Y} bis {end_date:%d.%m.%Y}")
    print(f"Koordinaten: {latitude}, {longitude}")
    print(f"Zeitzone: {timezone}")

    if not skip_forecast:
        print("\nLade historische 15-Minuten-Forecast-Daten...")
        fetch_historical_forecast(start_date, end_date, latitude, longitude, timezone, forecast_output)

    if not skip_secondary_forecast:
        print(f"\nLade zweite historische Forecast-Quelle ({secondary_forecast_model})...")
        fetch_historical_forecast(
            start_date,
            end_date,
            latitude,
            longitude,
            timezone,
            secondary_forecast_output,
            secondary_forecast_model,
            f"open_meteo_historical_forecast_15min_{secondary_forecast_model}",
        )

    if not skip_observed:
        print("\nLade tatsaechliche historische Mess-/Reanalysewerte...")
        fetch_observed_weather(start_date, end_date, latitude, longitude, timezone, observed_output)

    print("\nWetterdaten fertig.")


def main():
    parser = argparse.ArgumentParser(
        description="Laedt Open-Meteo-Wetterdaten passend zu den SunnyPortal-PV-Daten."
    )
    parser.add_argument("--start", type=date_arg, default=START_DATE, help="Startdatum YYYY-MM-DD")
    parser.add_argument("--end", type=date_arg, default=END_DATE, help="Enddatum YYYY-MM-DD")
    parser.add_argument("--latitude", type=float, default=LATITUDE, help="Breitengrad der PV-Anlage")
    parser.add_argument("--longitude", type=float, default=LONGITUDE, help="Laengengrad der PV-Anlage")
    parser.add_argument("--timezone", default=TIMEZONE, help="Zeitzone, z.B. Europe/Vienna")
    parser.add_argument("--forecast-output", type=Path, default=WEATHER_FORECAST_OUTPUT)
    parser.add_argument("--secondary-forecast-output", type=Path, default=WEATHER_SECONDARY_FORECAST_OUTPUT)
    parser.add_argument("--secondary-forecast-model", default=WEATHER_SECONDARY_FORECAST_MODEL)
    parser.add_argument("--observed-output", type=Path, default=WEATHER_OBSERVED_OUTPUT)
    parser.add_argument("--skip-forecast", action="store_true", help="Keine Forecast-Datei laden")
    parser.add_argument("--skip-secondary-forecast", action="store_true", help="Keine zweite Forecast-Datei laden")
    parser.add_argument("--skip-observed", action="store_true", help="Keine Messwerte-Datei laden")
    args = parser.parse_args()

    latitude = require_coordinate(args.latitude, "Latitude")
    longitude = require_coordinate(args.longitude, "Longitude")
    if args.end < args.start:
        raise SystemExit("Enddatum liegt vor dem Startdatum.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    scrape_weather(
        args.start,
        args.end,
        latitude,
        longitude,
        args.timezone,
        args.forecast_output,
        args.secondary_forecast_output,
        args.secondary_forecast_model,
        args.observed_output,
        args.skip_forecast,
        args.skip_secondary_forecast,
        args.skip_observed,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(130)
