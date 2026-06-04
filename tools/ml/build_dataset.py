#!/usr/bin/env python3
"""Erzeugt einen ML-Datensatz aus PV-Messdaten und Wetter-Forecasts."""

import argparse
import csv
import math
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    LATITUDE,
    LONGITUDE,
    ML_DATASET_OUTPUT,
    ML_END_DATE,
    ML_START_DATE,
    PV_MEASUREMENTS_CSV,
    PV_PANEL_AZIMUTH_DEG,
    PV_PANEL_TILT_DEG,
    TIMEZONE,
    WEATHER_FORECAST_OUTPUT,
    WEATHER_SECONDARY_FORECAST_OUTPUT,
)

# Physikalische Zusatzfeatures. Ausrichtung/Neigung kommen aus config/settings.py
# bzw. aus .env, damit du sie spaeter leicht anpassen kannst.
USE_PHYSICAL_FEATURES = True
CLEAR_SKY_BASE_IRRADIANCE_W_M2 = 1098.0
CLEAR_SKY_OPTICAL_DEPTH = 0.059
MAX_PANEL_IRRADIANCE_RATIO = 1.6
MAX_CLEAR_SKY_INDEX = 2.0
MAX_CLEAR_SKY_POWER_FACTOR = 1.15

FORECAST_METADATA_COLUMNS = {
    "timestamp",
    "date",
    "time",
    "source",
    "latitude",
    "longitude",
    "elevation",
    "timezone",
}
OUTPUT_BASE_COLUMNS = [
    "timestamp",
    "date",
    "time",
    "hour",
    "minute",
    "day_of_week",
    "month",
    "day_of_year",
    "hour_sin",
    "hour_cos",
    "day_of_year_sin",
    "day_of_year_cos",
    "solar_elevation_deg",
    "solar_azimuth_deg",
    "solar_zenith_deg",
    "solar_incidence_angle_deg",
    "solar_incidence_cos",
    "clear_sky_horizontal_irradiance",
    "clear_sky_panel_irradiance",
    "forecast_clear_sky_index",
    "icon_clear_sky_index",
    "forecast_panel_irradiance_ratio",
    "icon_panel_irradiance_ratio",
    "pv_observed_peak_w",
    "pv_clear_sky_power_estimate_w",
    "target_pv_power_generation_w",
    "pv_measurement_source",
]

COLUMN_METADATA = {
    "timestamp": ("datetime", "index", "Lokaler Zeitstempel des 15-Minuten-Slots."),
    "date": ("date", "index", "Lokales Datum des Slots."),
    "time": ("HH:MM", "index", "Lokale Uhrzeit des Slots."),
    "hour": ("0-23", "feature_time", "Stunde des Tages."),
    "minute": ("0,15,30,45", "feature_time", "Minute innerhalb der Stunde."),
    "day_of_week": ("0=Mon ... 6=Sun", "feature_time", "Wochentag."),
    "month": ("1-12", "feature_time", "Monat."),
    "day_of_year": ("1-366", "feature_time", "Tag im Jahr."),
    "hour_sin": ("unitless", "feature_time", "Zyklische Tageszeit-Komponente."),
    "hour_cos": ("unitless", "feature_time", "Zyklische Tageszeit-Komponente."),
    "day_of_year_sin": ("unitless", "feature_time", "Zyklische Jahreszeit-Komponente."),
    "day_of_year_cos": ("unitless", "feature_time", "Zyklische Jahreszeit-Komponente."),
    "solar_elevation_deg": ("degree", "feature_physical", "Berechnete Sonnenhoehe am Anlagenstandort."),
    "solar_azimuth_deg": ("degree", "feature_physical", "Berechneter Sonnenazimut, 0=Norden, 90=Osten."),
    "solar_zenith_deg": ("degree", "feature_physical", "Berechneter Sonnenzenitwinkel."),
    "solar_incidence_angle_deg": ("degree", "feature_physical", "Winkel zwischen Sonne und Modulnormalen."),
    "solar_incidence_cos": ("unitless", "feature_physical", "Kosinus des Einfallswinkels auf die Modulflaeche."),
    "clear_sky_horizontal_irradiance": ("W/m^2", "feature_physical", "Einfache wolkenfreie Globalstrahlung auf horizontaler Flaeche."),
    "clear_sky_panel_irradiance": ("W/m^2", "feature_physical", "Einfache wolkenfreie Einstrahlung auf der Modulflaeche."),
    "forecast_clear_sky_index": ("unitless", "feature_physical", "Forecast-Shortwave geteilt durch wolkenfreie Horizontalstrahlung."),
    "icon_clear_sky_index": ("unitless", "feature_physical", "ICON-Shortwave geteilt durch wolkenfreie Horizontalstrahlung."),
    "forecast_panel_irradiance_ratio": ("unitless", "feature_physical", "Forecast-Global-Tilted geteilt durch wolkenfreie Modulflächenstrahlung."),
    "icon_panel_irradiance_ratio": ("unitless", "feature_physical", "ICON-Global-Tilted geteilt durch wolkenfreie Modulflächenstrahlung."),
    "pv_observed_peak_w": ("W", "feature_physical", "Hoechste bisher beobachtete PV-Leistung in den PV-Messdaten."),
    "pv_clear_sky_power_estimate_w": ("W", "feature_physical", "Grobe Leistungsschaetzung aus wolkenfreier Modulflächenstrahlung und beobachtetem Peak."),
    "target_pv_power_generation_w": ("W", "target", "Gemessene PV-Leistung."),
    "pv_measurement_source": ("text", "metadata", "Optionale Quelle des Messwerts."),
    "forecast_temperature_2m": ("degC", "feature_forecast", "Vorhergesagte Lufttemperatur in 2 m Hoehe."),
    "forecast_relative_humidity_2m": ("%", "feature_forecast", "Vorhergesagte relative Luftfeuchtigkeit in 2 m Hoehe."),
    "forecast_dew_point_2m": ("degC", "feature_forecast", "Vorhergesagter Taupunkt in 2 m Hoehe."),
    "forecast_apparent_temperature": ("degC", "feature_forecast", "Vorhergesagte gefuehlte Temperatur."),
    "forecast_precipitation": ("mm", "feature_forecast", "Vorhergesagte Niederschlagsmenge im Slot."),
    "forecast_rain": ("mm", "feature_forecast", "Vorhergesagte Regenmenge im Slot."),
    "forecast_snowfall": ("cm", "feature_forecast", "Vorhergesagte Schneefallmenge im Slot."),
    "forecast_snow_depth": ("m", "feature_forecast", "Vorhergesagte Schneehoehe."),
    "forecast_weather_code": ("WMO code", "feature_forecast", "Vorhergesagter Wetterzustand als WMO-Code."),
    "forecast_pressure_msl": ("hPa", "feature_forecast", "Vorhergesagter Luftdruck auf Meeresspiegelniveau."),
    "forecast_surface_pressure": ("hPa", "feature_forecast", "Vorhergesagter Luftdruck an der Oberflaeche."),
    "forecast_cloud_cover": ("%", "feature_forecast", "Vorhergesagte Gesamtbedeckung durch Wolken."),
    "forecast_cloud_cover_low": ("%", "feature_forecast", "Vorhergesagte niedrige Wolkenbedeckung."),
    "forecast_cloud_cover_mid": ("%", "feature_forecast", "Vorhergesagte mittlere Wolkenbedeckung."),
    "forecast_cloud_cover_high": ("%", "feature_forecast", "Vorhergesagte hohe Wolkenbedeckung."),
    "forecast_vapour_pressure_deficit": ("kPa", "feature_forecast", "Vorhergesagtes Dampfdruckdefizit."),
    "forecast_et0_fao_evapotranspiration": ("mm", "feature_forecast", "Vorhergesagte Referenz-Evapotranspiration nach FAO."),
    "forecast_wind_speed_10m": ("km/h", "feature_forecast", "Vorhergesagte Windgeschwindigkeit in 10 m Hoehe."),
    "forecast_wind_speed_80m": ("km/h", "feature_forecast", "Vorhergesagte Windgeschwindigkeit in 80 m Hoehe."),
    "forecast_wind_speed_120m": ("km/h", "feature_forecast", "Vorhergesagte Windgeschwindigkeit in 120 m Hoehe."),
    "forecast_wind_speed_180m": ("km/h", "feature_forecast", "Vorhergesagte Windgeschwindigkeit in 180 m Hoehe."),
    "forecast_wind_direction_10m": ("degree", "feature_forecast", "Vorhergesagte Windrichtung in 10 m Hoehe."),
    "forecast_wind_direction_80m": ("degree", "feature_forecast", "Vorhergesagte Windrichtung in 80 m Hoehe."),
    "forecast_wind_direction_120m": ("degree", "feature_forecast", "Vorhergesagte Windrichtung in 120 m Hoehe."),
    "forecast_wind_direction_180m": ("degree", "feature_forecast", "Vorhergesagte Windrichtung in 180 m Hoehe."),
    "forecast_wind_gusts_10m": ("km/h", "feature_forecast", "Vorhergesagte Windboeen in 10 m Hoehe."),
    "forecast_visibility": ("m", "feature_forecast", "Vorhergesagte Sichtweite."),
    "forecast_shortwave_radiation": ("W/m^2", "feature_forecast", "Vorhergesagte globale kurzwellige Strahlung auf horizontaler Flaeche."),
    "forecast_direct_radiation": ("W/m^2", "feature_forecast", "Vorhergesagte direkte Strahlung auf horizontaler Flaeche."),
    "forecast_diffuse_radiation": ("W/m^2", "feature_forecast", "Vorhergesagte diffuse Strahlung auf horizontaler Flaeche."),
    "forecast_direct_normal_irradiance": ("W/m^2", "feature_forecast", "Vorhergesagte direkte Normalstrahlung."),
    "forecast_global_tilted_irradiance": ("W/m^2", "feature_forecast", "Vorhergesagte globale Strahlung auf geneigter Flaeche."),
    "forecast_terrestrial_radiation": ("W/m^2", "feature_forecast", "Vorhergesagte extraterrestrische Strahlung."),
    "forecast_is_day": ("0/1", "feature_forecast", "Vorhergesagter Tag/Nacht-Indikator."),
    "forecast_sunshine_duration": ("s", "feature_forecast", "Vorhergesagte Sonnenscheindauer im Slot."),
}


def parse_number(value):
    value = value.strip()
    if value == "":
        return ""
    value = value.replace("\ufeff", "").strip('"')
    value = value.replace(",", "")
    try:
        number = float(value)
    except ValueError:
        return ""
    if number.is_integer():
        return int(number)
    return number


def iter_expected_timestamps(start_date, end_date):
    current = datetime.combine(start_date.date(), time(0, 0))
    end = datetime.combine(end_date.date(), time(23, 45))
    while current <= end:
        yield current
        current += timedelta(minutes=15)


def read_pv_measurements(path):
    if not path.exists():
        raise SystemExit(
            f"PV measurement file missing: {path}\n"
            "Create it with pv_measurements.py or provide your own CSV with "
            "timestamp,pv_power_w."
        )

    rows_by_timestamp = {}
    duplicate_timestamps = []
    empty_targets = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        required = {"timestamp", "pv_power_w"}
        missing = required - fieldnames
        if missing:
            raise SystemExit(
                f"PV measurement file is missing columns {sorted(missing)}: {path}"
            )

        for row in reader:
            timestamp = datetime.fromisoformat(row["timestamp"])
            target = parse_number(row["pv_power_w"])
            if target == "":
                empty_targets.append((timestamp, path.name))
                continue

            if timestamp in rows_by_timestamp:
                duplicate_timestamps.append(timestamp)
                continue

            rows_by_timestamp[timestamp] = {
                "target_pv_power_generation_w": target,
                "pv_measurement_source": row.get("source", ""),
            }

    return rows_by_timestamp, duplicate_timestamps, empty_targets


def read_forecast(path, column_prefix):
    if not path.exists():
        raise SystemExit(f"Forecast-Datei fehlt: {path}")

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise SystemExit(f"Forecast-Datei hat keinen Header: {path}")

        forecast_columns = [
            column for column in reader.fieldnames
            if column not in FORECAST_METADATA_COLUMNS
        ]
        rows_by_timestamp = {}
        duplicate_timestamps = []

        for row in reader:
            timestamp = datetime.fromisoformat(row["timestamp"])
            if timestamp in rows_by_timestamp:
                duplicate_timestamps.append(timestamp)
                continue
            rows_by_timestamp[timestamp] = {
                f"{column_prefix}_{column}": row[column]
                for column in forecast_columns
            }

    return rows_by_timestamp, [f"{column_prefix}_{column}" for column in forecast_columns], duplicate_timestamps


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def safe_float(value, default=0.0):
    parsed = parse_number(str(value))
    return default if parsed == "" else float(parsed)


def empty_physical_solar_features():
    return {
        "solar_elevation_deg": 0.0,
        "solar_azimuth_deg": 0.0,
        "solar_zenith_deg": 90.0,
        "solar_incidence_angle_deg": 90.0,
        "solar_incidence_cos": 0.0,
        "clear_sky_horizontal_irradiance": 0.0,
        "clear_sky_panel_irradiance": 0.0,
    }


def solar_position(timestamp):
    if not USE_PHYSICAL_FEATURES or LATITUDE is None or LONGITUDE is None:
        return empty_physical_solar_features()

    timezone = ZoneInfo(TIMEZONE)
    aware_timestamp = timestamp.replace(tzinfo=timezone)
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
        + 4 * LONGITUDE
        - 60 * utc_offset_hours
    ) % 1440
    hour_angle_deg = true_solar_minutes / 4 - 180
    hour_angle = math.radians(hour_angle_deg)
    latitude = math.radians(LATITUDE)

    cos_zenith = (
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    cos_zenith = clamp(cos_zenith, -1.0, 1.0)
    zenith = math.degrees(math.acos(cos_zenith))
    elevation = 90 - zenith

    azimuth = (
        math.degrees(
            math.atan2(
                math.sin(hour_angle),
                math.cos(hour_angle) * math.sin(latitude)
                - math.tan(declination) * math.cos(latitude),
            )
        )
        + 180
    ) % 360

    elevation_rad = math.radians(elevation)
    azimuth_rad = math.radians(azimuth)
    panel_azimuth_rad = math.radians(PV_PANEL_AZIMUTH_DEG)
    panel_tilt_rad = math.radians(PV_PANEL_TILT_DEG)

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
        clear_sky_panel = clear_sky_horizontal * clamp(panel_ratio, 0.0, MAX_PANEL_IRRADIANCE_RATIO)
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


def build_solar_feature_rows(timestamps):
    return {
        timestamp: solar_position(timestamp)
        for timestamp in timestamps
    }


def physical_features(solar_features, forecast_row, secondary_forecast_row, observed_peak_w):
    features = dict(solar_features)
    clear_sky_horizontal = features["clear_sky_horizontal_irradiance"]
    clear_sky_panel = features["clear_sky_panel_irradiance"]
    forecast_shortwave = safe_float(forecast_row.get("forecast_shortwave_radiation", 0))
    icon_shortwave = safe_float(secondary_forecast_row.get("icon_shortwave_radiation", 0))
    forecast_panel = safe_float(forecast_row.get("forecast_global_tilted_irradiance", 0))
    icon_panel = safe_float(secondary_forecast_row.get("icon_global_tilted_irradiance", 0))

    features.update({
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
        "pv_clear_sky_power_estimate_w": observed_peak_w * clamp(
            clear_sky_panel / 1000.0,
            0.0,
            MAX_CLEAR_SKY_POWER_FACTOR,
        ),
    })
    return features


def time_features(timestamp):
    hour_float = timestamp.hour + timestamp.minute / 60
    day_of_year = timestamp.timetuple().tm_yday
    return {
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


def print_missing_warning(label, missing):
    if not missing:
        return
    print(f"WARNUNG: {len(missing)} erwartete Zeitstempel fehlen in {label}.")
    for timestamp in missing[:10]:
        print(f"  {timestamp}")
    if len(missing) > 10:
        print(f"  ... weitere {len(missing) - 10}")


def print_duplicate_warning(label, duplicates):
    if not duplicates:
        return
    unique_duplicates = sorted(set(duplicates))
    print(f"WARNUNG: {len(duplicates)} doppelte Zeitstempel in {label}; erste Werte wurden behalten.")
    for timestamp in unique_duplicates[:10]:
        print(f"  {timestamp}")
    if len(unique_duplicates) > 10:
        print(f"  ... weitere {len(unique_duplicates) - 10}")


def print_empty_target_warning(empty_targets):
    if not empty_targets:
        return
    print(f"WARNUNG: {len(empty_targets)} PV-Zeitpunkte haben keinen Target-Wert und werden uebersprungen.")
    for timestamp, filename in empty_targets[:10]:
        print(f"  {timestamp} in {filename}")
    if len(empty_targets) > 10:
        print(f"  ... weitere {len(empty_targets) - 10}")


def write_column_metadata(columns, output_path):
    metadata_path = output_path.with_name(f"{output_path.stem}_columns.csv")
    with metadata_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["column", "unit", "role", "description"],
        )
        writer.writeheader()
        for column in columns:
            unit, role, description = column_metadata(column)
            writer.writerow({
                "column": column,
                "unit": unit,
                "role": role,
                "description": description,
            })
    return metadata_path


def column_metadata(column):
    metadata = COLUMN_METADATA.get(column)
    if metadata:
        return metadata

    if column.startswith("icon_"):
        base_column = "forecast_" + column.removeprefix("icon_")
        base_metadata = COLUMN_METADATA.get(base_column)
        if base_metadata:
            unit, _role, description = base_metadata
            return unit, "feature_forecast", "ICON-EU: " + description
        return "", "feature_forecast", "ICON-EU Forecast-Feature."

    return "", "unknown", ""


def build_dataset(
    pv_measurements_path,
    forecast_path,
    secondary_forecast_path,
    output_path,
    start_date,
    end_date,
):
    print("Baue ML-Datensatz aus PV-Daten und Forecast-Daten...")
    print(f"PV-Messdatei: {pv_measurements_path}")
    print(f"Forecast-Datei: {forecast_path}")
    print(f"Zweite Forecast-Datei: {secondary_forecast_path}")
    print(f"Zeitraum: {start_date:%d.%m.%Y} bis {end_date:%d.%m.%Y}")

    pv_rows, pv_duplicates, empty_targets = read_pv_measurements(pv_measurements_path)
    observed_peak_w = max(
        float(row["target_pv_power_generation_w"])
        for row in pv_rows.values()
    )
    forecast_rows, forecast_columns, forecast_duplicates = read_forecast(forecast_path, "forecast")
    (
        secondary_forecast_rows,
        secondary_forecast_columns,
        secondary_forecast_duplicates,
    ) = read_forecast(secondary_forecast_path, "icon")
    expected_timestamps = list(iter_expected_timestamps(start_date, end_date))
    solar_features_by_timestamp = build_solar_feature_rows(expected_timestamps)

    print_duplicate_warning("PV-Daten", pv_duplicates)
    print_duplicate_warning("Forecast-Daten", forecast_duplicates)
    print_duplicate_warning("zweiten Forecast-Daten", secondary_forecast_duplicates)
    print_empty_target_warning(empty_targets)

    missing_pv = [timestamp for timestamp in expected_timestamps if timestamp not in pv_rows]
    missing_forecast = [timestamp for timestamp in expected_timestamps if timestamp not in forecast_rows]
    missing_secondary_forecast = [
        timestamp for timestamp in expected_timestamps
        if timestamp not in secondary_forecast_rows
    ]
    print_missing_warning("PV-Daten", missing_pv)
    print_missing_warning("Forecast-Daten", missing_forecast)
    print_missing_warning("zweiten Forecast-Daten", missing_secondary_forecast)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        *OUTPUT_BASE_COLUMNS,
        *forecast_columns,
        *secondary_forecast_columns,
    ]
    rows_written = 0
    skipped = 0

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for timestamp in expected_timestamps:
            pv_row = pv_rows.get(timestamp)
            forecast_row = forecast_rows.get(timestamp)
            secondary_forecast_row = secondary_forecast_rows.get(timestamp)
            if not pv_row or not forecast_row or not secondary_forecast_row:
                skipped += 1
                continue

            writer.writerow({
                **time_features(timestamp),
                **physical_features(
                    solar_features_by_timestamp[timestamp],
                    forecast_row,
                    secondary_forecast_row,
                    observed_peak_w,
                ),
                **pv_row,
                **forecast_row,
                **secondary_forecast_row,
            })
            rows_written += 1

    metadata_path = write_column_metadata(columns, output_path)

    print("\nML-Datensatz erstellt")
    print(f"PV-Messwerte gelesen: {len(pv_rows)}")
    print(f"Hoechste beobachtete PV-Leistung: {observed_peak_w:.0f} W")
    print(f"Erwartete 15-Minuten-Slots: {len(expected_timestamps)}")
    print(f"Geschriebene Zeilen: {rows_written}")
    print(f"Uebersprungene Slots wegen fehlender PV- oder Forecast-Daten: {skipped}")
    print(f"Ausgabe: {output_path}")
    print(f"Spaltenbeschreibung: {metadata_path}")
    return rows_written


def date_arg(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Datum muss im Format YYYY-MM-DD sein") from exc


def main():
    parser = argparse.ArgumentParser(
        description="Erzeugt einen ML-Datensatz aus PV-Messdaten und Open-Meteo-Forecasts."
    )
    parser.add_argument(
        "pv_measurements",
        nargs="?",
        type=Path,
        default=PV_MEASUREMENTS_CSV,
        help="CSV mit timestamp,pv_power_w. Standard: PV_MEASUREMENTS_CSV.",
    )
    parser.add_argument(
        "--forecast",
        type=Path,
        default=WEATHER_FORECAST_OUTPUT,
        help="Forecast-CSV. Standard: data/ml/features/weather_forecast_features.csv",
    )
    parser.add_argument(
        "--secondary-forecast",
        type=Path,
        default=WEATHER_SECONDARY_FORECAST_OUTPUT,
        help="Zweite Forecast-CSV. Standard: data/ml/features/weather_forecast_icon_features.csv",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ML_DATASET_OUTPUT,
        help="Ausgabedatei. Standard: data/ml/ml_pv_forecast_dataset.csv",
    )
    parser.add_argument("--start", type=date_arg, default=ML_START_DATE, help="Startdatum YYYY-MM-DD")
    parser.add_argument("--end", type=date_arg, default=ML_END_DATE, help="Enddatum YYYY-MM-DD")
    args = parser.parse_args()

    if args.end < args.start:
        raise SystemExit("Enddatum liegt vor dem Startdatum.")

    build_dataset(
        args.pv_measurements,
        args.forecast,
        args.secondary_forecast,
        args.output,
        args.start,
        args.end,
    )


if __name__ == "__main__":
    main()
