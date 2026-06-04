"""Simple local smoke test.

Run from the repository root:
python3 custom_components/pv_forecast_planner/tests.py
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import types

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "implementationRaw" / "models" / "pv_forecast_xgboost"
COMPONENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(COMPONENT_DIR / "pv"))

package_name = "custom_components.pv_forecast_planner"
custom_components = types.ModuleType("custom_components")
package = types.ModuleType(package_name)
package.__path__ = [str(COMPONENT_DIR)]
sys.modules.setdefault("custom_components", custom_components)
sys.modules.setdefault(package_name, package)

LATITUDE = 48.2082
LONGITUDE = 16.3738
TIMEZONE = "Europe/Vienna"
PANEL_AZIMUTH_DEG = 350.0
PANEL_TILT_DEG = 45.0

from features import build_feature_matrix, build_feature_rows  # noqa: E402
from custom_components.pv_forecast_planner.pv.forecast import (  # noqa: E402
    PvForecastConfig,
    create_pv_forecast,
)
from custom_components.pv_forecast_planner.pv.model import PvForecastModel  # noqa: E402
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
    compare_model_backends(matrix[:3])

    result = create_pv_forecast(
        PvForecastConfig(
            model_dir=MODEL_DIR,
            latitude=LATITUDE,
            longitude=LONGITUDE,
            timezone=TIMEZONE,
            panel_azimuth_deg=PANEL_AZIMUTH_DEG,
            panel_tilt_deg=PANEL_TILT_DEG,
            forecast_days=1,
            secondary_forecast_model="icon_eu",
        ),
        now=datetime.now(),
    )

    print(f"forecast current slot: {result.current_slot}")
    print(f"forecast current power W: {round(result.current_power_w, 1)}")
    print(f"forecast points: {len(result.forecast_points)}")
    print(f"forecast total energy kWh: {round(result.total_energy_kwh, 3)}")


def compare_model_backends(sample_matrix: list[list[float]]) -> None:
    """Compare pure Python and optional XGBoost backend when xgboost is installed."""
    python_model = PvForecastModel(MODEL_DIR)
    python_predictions = python_model.predict(sample_matrix)

    try:
        xgboost_model = PvForecastModel(MODEL_DIR, backend="xgboost")
        xgboost_predictions = xgboost_model.predict(sample_matrix)
    except ImportError:
        print("xgboost backend comparison skipped: xgboost is not installed locally")
        return

    max_diff = max(
        abs(python_value - xgboost_value)
        for python_value, xgboost_value in zip(python_predictions, xgboost_predictions)
    )
    print(f"xgboost backend max diff W: {max_diff:.6f}")


if __name__ == "__main__":
    main()
