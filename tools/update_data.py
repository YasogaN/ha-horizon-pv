#!/usr/bin/env python3
"""Aktualisiert historische PV- und Wetterdaten fuer Training."""

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def run_step(command, title):
    print(f"\n== {title} ==", flush=True)
    print(" ".join(str(part) for part in command), flush=True)
    subprocess.run(command, cwd=PROJECT_DIR, check=True)


def main():
    parser = argparse.ArgumentParser(description="Laedt/aktualisiert historische PV- und Wetterdaten.")
    parser.add_argument("--skip-pv", action="store_true", help="SunnyPortal Energy-Balance-Daten nicht laden.")
    parser.add_argument("--skip-weather", action="store_true", help="Historische Wetterdaten nicht laden.")
    parser.add_argument("--skip-dataset", action="store_true", help="ML-Datensatz danach nicht neu bauen.")
    args = parser.parse_args()

    if not args.skip_pv:
        run_step([sys.executable, "scrapers/sunnyportal.py"], "SunnyPortal-Daten aktualisieren")

    if not args.skip_weather:
        run_step([sys.executable, "scrapers/weather.py"], "Historische Wetterdaten aktualisieren")

    if not args.skip_dataset:
        run_step([sys.executable, "ml/build_dataset.py"], "ML-Datensatz bauen")

    print("\nDatenaktualisierung fertig.")


if __name__ == "__main__":
    main()
