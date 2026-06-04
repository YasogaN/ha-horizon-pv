#!/usr/bin/env python3
"""Baut den ML-Datensatz und trainiert das PV-Prognosemodell."""

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
    parser = argparse.ArgumentParser(description="Baut Dataset und trainiert das finale Modell.")
    parser.add_argument("--skip-dataset", action="store_true", help="Vorhandenen ML-Datensatz verwenden.")
    args = parser.parse_args()

    if not args.skip_dataset:
        run_step([sys.executable, "ml/build_dataset.py"], "ML-Datensatz bauen")

    run_step([sys.executable, "ml/train_model.py"], "XGBoost-Modell trainieren")
    print("\nTraining fertig.")


if __name__ == "__main__":
    main()
