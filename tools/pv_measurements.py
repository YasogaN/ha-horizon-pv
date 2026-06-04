#!/usr/bin/env python3
"""Build the generic PV measurements CSV from SunnyPortal raw files."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, time, timedelta
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PV_MEASUREMENTS_CSV, SUNNYPORTAL_RAW_DIR

FILENAME_RE = re.compile(r"Energy_Balance_(\d{4})_(\d{2})_(\d{2})\.csv$")


def parse_date_from_filename(path: Path):
    match = FILENAME_RE.match(path.name)
    if not match:
        raise ValueError(f"Filename does not match SunnyPortal format: {path.name}")
    year, month, day = map(int, match.groups())
    return datetime(year, month, day).date()


def parse_time_cell(value: str):
    value = value.strip()
    if value.startswith("="):
        value = value[1:]
    value = value.strip('"')
    return datetime.strptime(value, "%H:%M").time()


def parse_number(value: str):
    value = value.strip()
    if value == "":
        return None
    value = value.replace("\ufeff", "").strip('"')
    value = value.replace(",", "")
    try:
        return float(value)
    except ValueError:
        return None


def collect_sunnyportal_files(input_dir: Path, recursive: bool = False):
    pattern = "**/Energy_Balance_*.csv" if recursive else "Energy_Balance_*.csv"
    return sorted(
        (path for path in input_dir.glob(pattern) if FILENAME_RE.match(path.name)),
        key=parse_date_from_filename,
    )


def read_sunnyportal_measurements(input_dir: Path, recursive: bool = False):
    rows_by_timestamp = {}
    duplicates = []
    empty_values = []
    files = collect_sunnyportal_files(input_dir, recursive)
    if not files:
        raise SystemExit(f"No Energy_Balance_YYYY_MM_DD.csv files found in {input_dir}")

    for path in files:
        day = parse_date_from_filename(path)
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file, delimiter=";")
            header = next(reader, None)
            if not header:
                print(f"WARNING: Empty SunnyPortal file: {path.name}")
                continue

            for row_number, row in enumerate(reader, start=1):
                if len(row) < 9 or not row[0].strip():
                    continue

                slot_time = parse_time_cell(row[0])
                timestamp_day = day
                if row_number > 1 and slot_time == time(0, 0):
                    timestamp_day = day + timedelta(days=1)
                timestamp = datetime.combine(timestamp_day, slot_time)
                pv_power_w = parse_number(row[8])
                if pv_power_w is None:
                    empty_values.append((timestamp, path.name))
                    continue

                if timestamp in rows_by_timestamp:
                    duplicates.append(timestamp)
                    continue

                rows_by_timestamp[timestamp] = {
                    "timestamp": timestamp,
                    "pv_power_w": pv_power_w,
                    "source": path.name,
                }

    return rows_by_timestamp, files, duplicates, empty_values


def write_measurements(rows_by_timestamp, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["timestamp", "pv_power_w", "source"],
        )
        writer.writeheader()
        for timestamp in sorted(rows_by_timestamp):
            row = rows_by_timestamp[timestamp]
            writer.writerow(
                {
                    "timestamp": timestamp.isoformat(sep=" "),
                    "pv_power_w": round(float(row["pv_power_w"]), 3),
                    "source": row["source"],
                }
            )


def main():
    parser = argparse.ArgumentParser(
        description="Converts SunnyPortal raw Energy Balance CSVs to generic PV measurements."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=SUNNYPORTAL_RAW_DIR,
        help="Directory with SunnyPortal Energy_Balance_YYYY_MM_DD.csv files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=PV_MEASUREMENTS_CSV,
        help="Generic output CSV with timestamp,pv_power_w,source.",
    )
    parser.add_argument("--recursive", action="store_true", help="Search input directory recursively.")
    args = parser.parse_args()

    rows_by_timestamp, files, duplicates, empty_values = read_sunnyportal_measurements(
        args.input_dir,
        args.recursive,
    )
    write_measurements(rows_by_timestamp, args.output)

    print("PV measurements CSV created")
    print(f"SunnyPortal files: {len(files)}")
    print(f"Rows: {len(rows_by_timestamp)}")
    print(f"Duplicate timestamps skipped: {len(duplicates)}")
    print(f"Empty PV values skipped: {len(empty_values)}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
