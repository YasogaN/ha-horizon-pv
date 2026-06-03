"""Simple local smoke test.

Run from the repository root:
python3 custom_components/pv_forecast_planner/tests.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "implementationRaw" / "models" / "pv_forecast_xgboost"
COMPONENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(COMPONENT_DIR / "pv"))

LATITUDE = 48.2082
LONGITUDE = 16.3738
TIMEZONE = "Europe/Vienna"
PANEL_AZIMUTH_DEG = 350.0
PANEL_TILT_DEG = 45.0

from features import build_feature_matrix, build_feature_rows  # noqa: E402
from weather import fetch_open_meteo_forecast  # noqa: E402


def main() -> None:
    with (MODEL_DIR / "features.json").open("r", encoding="utf-8") as file:
        metadata = json.load(file)

    primary = fetch_open_meteo_forecast(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        timezone=TIMEZONE,
        forecast_days=1,
    )
    icon = fetch_open_meteo_forecast(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        timezone=TIMEZONE,
        forecast_days=1,
        model="icon_eu",
    )

    rows = build_feature_rows(
        primary,
        icon,
        observed_peak_w=float(metadata["observed_peak_w"]),
        latitude=LATITUDE,
        longitude=LONGITUDE,
        timezone=TIMEZONE,
        panel_azimuth_deg=PANEL_AZIMUTH_DEG,
        panel_tilt_deg=PANEL_TILT_DEG,
    )
    matrix = build_feature_matrix(rows, metadata["feature_columns"])

    noon = next(ts for ts in primary if ts.hour == 12 and ts.minute == 0)

    print(f"primary rows: {len(primary)}")
    print(f"icon rows: {len(icon)}")
    print(f"noon primary shortwave: {primary[noon]['shortwave_radiation']}")
    print(f"noon icon shortwave: {icon[noon]['shortwave_radiation']}")
    print(f"feature rows: {len(rows)}")
    print(f"feature columns: {len(matrix[0])}")
    print(f"first timestamp: {rows[0]['_timestamp']}")
    print(f"last timestamp: {rows[-1]['_timestamp']}")


if __name__ == "__main__":
    main()
