#!/usr/bin/env python3
"""Trainiert das finale XGBoost-Modell fuer die PV-Leistungsprognose."""

import csv
import json
import math
import random
import shutil
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    ACTIVE_PV_THRESHOLD_W,
    ML_DATASET_OUTPUT,
    MODEL_DIR,
    NEIGHBOR_OFFSETS,
    SAFE_PREDICTION_FACTOR,
    SAVE_FEATURE_IMPORTANCE,
    USE_NEIGHBOR_DELTAS,
    USE_NEIGHBOR_FEATURES,
    XGB_COLSAMPLE_BYTREE,
    XGB_LEARNING_RATE,
    XGB_MAX_DEPTH,
    XGB_MIN_CHILD_WEIGHT,
    XGB_N_ESTIMATORS,
    XGB_N_JOBS,
    XGB_OBJECTIVE,
    XGB_RANDOM_STATE,
    XGB_REG_LAMBDA,
    XGB_SUBSAMPLE,
)

DATASET_PATH = ML_DATASET_OUTPUT
COLUMNS_PATH = ML_DATASET_OUTPUT.with_name(f"{ML_DATASET_OUTPUT.stem}_columns.csv")
PLOTS_DIR = MODEL_DIR / "plots"
DIAGNOSTICS_DIR = MODEL_DIR / "diagnostics"

TARGET_COLUMN = "target_pv_power_generation_w"

MODEL_PARAMS = {
    "n_estimators": XGB_N_ESTIMATORS,
    "max_depth": XGB_MAX_DEPTH,
    "learning_rate": XGB_LEARNING_RATE,
    "subsample": XGB_SUBSAMPLE,
    "colsample_bytree": XGB_COLSAMPLE_BYTREE,
    "min_child_weight": XGB_MIN_CHILD_WEIGHT,
    "reg_lambda": XGB_REG_LAMBDA,
}

NEIGHBOR_BASE_COLUMNS = [
    "solar_elevation_deg",
    "solar_incidence_cos",
    "clear_sky_horizontal_irradiance",
    "clear_sky_panel_irradiance",
    "forecast_clear_sky_index",
    "icon_clear_sky_index",
    "forecast_panel_irradiance_ratio",
    "icon_panel_irradiance_ratio",
    "pv_clear_sky_power_estimate_w",
    "forecast_shortwave_radiation",
    "forecast_direct_radiation",
    "forecast_diffuse_radiation",
    "forecast_direct_normal_irradiance",
    "forecast_global_tilted_irradiance",
    "forecast_cloud_cover",
    "forecast_cloud_cover_low",
    "forecast_cloud_cover_mid",
    "forecast_cloud_cover_high",
    "forecast_sunshine_duration",
    "icon_shortwave_radiation",
    "icon_direct_radiation",
    "icon_diffuse_radiation",
    "icon_direct_normal_irradiance",
    "icon_global_tilted_irradiance",
    "icon_cloud_cover",
    "icon_cloud_cover_low",
    "icon_cloud_cover_mid",
    "icon_cloud_cover_high",
    "icon_sunshine_duration",
]


def read_column_roles():
    with COLUMNS_PATH.open("r", encoding="utf-8", newline="") as file:
        return {
            row["column"]: row["role"]
            for row in csv.DictReader(file)
        }


def load_dataset_rows():
    column_roles = read_column_roles()
    with DATASET_PATH.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = sorted(reader, key=lambda row: row["timestamp"])
        dataset_header = reader.fieldnames or []

    base_feature_columns = [
        column
        for column in dataset_header
        if column_roles.get(column) in {"feature_time", "feature_forecast", "feature_physical"}
        and column not in {"timestamp", "date", "time", "pv_measurement_source", TARGET_COLUMN}
    ]
    neighbor_columns = (
        [
            column for column in NEIGHBOR_BASE_COLUMNS
            if column in base_feature_columns
        ]
        if USE_NEIGHBOR_FEATURES
        else []
    )
    return rows, base_feature_columns, neighbor_columns


def value_at(rows, index, column):
    if index < 0:
        index = 0
    elif index >= len(rows):
        index = len(rows) - 1
    return float(rows[index][column])


def build_feature_matrix(rows, base_feature_columns, neighbor_columns):
    feature_columns = list(base_feature_columns)
    for column in neighbor_columns:
        for offset in NEIGHBOR_OFFSETS:
            suffix = f"prev_{abs(offset)}" if offset < 0 else f"next_{offset}"
            feature_columns.append(f"{column}_{suffix}")
        if USE_NEIGHBOR_DELTAS:
            feature_columns.append(f"{column}_delta_prev_1")
            feature_columns.append(f"{column}_delta_next_1")

    features = []
    targets = []
    timestamps = []
    is_day_values = []
    radiation_values = []

    for index, row in enumerate(rows):
        current_features = [float(row[column]) for column in base_feature_columns]
        for column in neighbor_columns:
            current_value = float(row[column])
            for offset in NEIGHBOR_OFFSETS:
                current_features.append(value_at(rows, index + offset, column))
            if USE_NEIGHBOR_DELTAS:
                current_features.append(current_value - value_at(rows, index - 1, column))
                current_features.append(value_at(rows, index + 1, column) - current_value)

        features.append(current_features)
        targets.append(float(row[TARGET_COLUMN]))
        timestamps.append(row["timestamp"])
        is_day_values.append(float(row.get("forecast_is_day", 0.0)))
        radiation_values.append(float(row.get("forecast_shortwave_radiation", 0.0)))

    return {
        "features": features,
        "target": targets,
        "timestamps": timestamps,
        "is_day": is_day_values,
        "radiation": radiation_values,
        "feature_columns": feature_columns,
    }


def split_dataset(data):
    row_count = len(data["target"])
    train_end = int(row_count * 0.70)
    validation_end = int(row_count * 0.85)

    ranges = {
        "train": (0, train_end),
        "validation": (train_end, validation_end),
        "test": (validation_end, row_count),
    }
    splits = {}
    for split_name, (start, end) in ranges.items():
        splits[split_name] = {
            key: value[start:end]
            for key, value in data.items()
            if key != "feature_columns"
        }
        splits[split_name]["feature_columns"] = data["feature_columns"]
    return splits


def create_model():
    return XGBRegressor(
        objective=XGB_OBJECTIVE,
        **MODEL_PARAMS,
        n_jobs=XGB_N_JOBS,
        random_state=XGB_RANDOM_STATE,
    )


def predict_split(model, split_data):
    return [
        max(0.0, prediction)
        for prediction in model.predict(split_data["features"])
    ]


def safe_predictions(predictions):
    return [
        max(0.0, prediction * SAFE_PREDICTION_FACTOR)
        for prediction in predictions
    ]


def metric_values(target, predictions, mask=None):
    if mask is None:
        pairs = list(zip(target, predictions))
    else:
        pairs = [
            (actual, prediction)
            for actual, prediction, keep in zip(target, predictions, mask)
            if keep
        ]

    if not pairs:
        return {
            "count": 0,
            "mae_w": 0.0,
            "rmse_w": 0.0,
            "over_mae_w": 0.0,
            "under_mae_w": 0.0,
            "over_energy_kwh": 0.0,
            "under_energy_kwh": 0.0,
        }

    errors = [prediction - actual for actual, prediction in pairs]
    over_errors = [max(0.0, error) for error in errors]
    under_errors = [max(0.0, -error) for error in errors]
    return {
        "count": len(pairs),
        "mae_w": sum(abs(error) for error in errors) / len(errors),
        "rmse_w": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "over_mae_w": sum(over_errors) / len(over_errors),
        "under_mae_w": sum(under_errors) / len(under_errors),
        "over_energy_kwh": sum(over_errors) * 0.25 / 1000,
        "under_energy_kwh": sum(under_errors) * 0.25 / 1000,
    }


def evaluate_split(split_data, predictions):
    daylight_mask = [
        is_day > 0 or radiation > 50
        for is_day, radiation in zip(split_data["is_day"], split_data["radiation"])
    ]
    active_mask = [
        actual > ACTIVE_PV_THRESHOLD_W
        for actual in split_data["target"]
    ]
    return {
        "all": metric_values(split_data["target"], predictions),
        "daylight": metric_values(split_data["target"], predictions, daylight_mask),
        "active_pv": metric_values(split_data["target"], predictions, active_mask),
    }


def save_feature_importance(model, feature_columns):
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    importance_path = DIAGNOSTICS_DIR / "feature_importance.csv"
    importances = model.feature_importances_
    rows = sorted(
        zip(feature_columns, importances),
        key=lambda item: item[1],
        reverse=True,
    )
    with importance_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["feature", "importance"])
        writer.writerows(rows)
    return importance_path


def save_test_predictions(split_data, predictions, safe_values):
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    predictions_path = DIAGNOSTICS_DIR / "test_predictions.csv"
    with predictions_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp",
            "actual_w",
            "predicted_w",
            "safe_predicted_w",
            "error_w",
            "safe_error_w",
            "over_w",
            "under_w",
            "safe_over_w",
            "safe_under_w",
            "forecast_shortwave_radiation",
            "icon_shortwave_radiation",
        ])
        feature_columns = split_data["feature_columns"]
        icon_radiation_index = (
            feature_columns.index("icon_shortwave_radiation")
            if "icon_shortwave_radiation" in feature_columns
            else None
        )
        forecast_radiation_index = (
            feature_columns.index("forecast_shortwave_radiation")
            if "forecast_shortwave_radiation" in feature_columns
            else None
        )
        for timestamp, actual, prediction, safe_prediction, features in zip(
            split_data["timestamps"],
            split_data["target"],
            predictions,
            safe_values,
            split_data["features"],
        ):
            error = prediction - actual
            safe_error = safe_prediction - actual
            writer.writerow([
                timestamp,
                actual,
                prediction,
                safe_prediction,
                error,
                safe_error,
                max(0.0, error),
                max(0.0, -error),
                max(0.0, safe_error),
                max(0.0, -safe_error),
                features[forecast_radiation_index] if forecast_radiation_index is not None else "",
                features[icon_radiation_index] if icon_radiation_index is not None else "",
            ])
    return predictions_path


def plot_test_predictions(timestamps, actual_values, predicted_values, safe_values, max_daily_plots=5):
    if PLOTS_DIR.exists():
        shutil.rmtree(PLOTS_DIR)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    plot_curve(
        timestamps,
        actual_values,
        predicted_values,
        safe_values,
        PLOTS_DIR / "test_all.png",
        "XGBoost Neighbor Testzeitraum: Ist vs. Prognose",
    )

    rows_by_date = {}
    for timestamp, actual, predicted, safe_prediction in zip(
        timestamps,
        actual_values,
        predicted_values,
        safe_values,
    ):
        date = timestamp.split(" ", 1)[0]
        rows_by_date.setdefault(date, []).append((timestamp, actual, predicted, safe_prediction))

    selected_dates = random.sample(
        sorted(rows_by_date),
        k=min(max_daily_plots, len(rows_by_date)),
    )
    for date in selected_dates:
        day_rows = rows_by_date[date]
        day_timestamps, day_actual, day_predicted, day_safe = zip(*day_rows)
        plot_curve(
            day_timestamps,
            day_actual,
            day_predicted,
            day_safe,
            PLOTS_DIR / f"test_day_{date}.png",
            f"XGBoost Neighbor {date}: Ist vs. Prognose",
        )


def plot_curve(timestamps, actual_values, predicted_values, safe_values, output_path, title):
    times = [datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S") for timestamp in timestamps]
    plt.figure(figsize=(14, 6), facecolor="white")
    plt.plot(times, actual_values, label="Ist", linewidth=1.8)
    plt.plot(times, predicted_values, label="Prognose", linewidth=1.8)
    plt.plot(times, safe_values, label="Safe Prognose", linewidth=1.6, linestyle="--")
    plt.title(title)
    plt.xlabel("Zeit")
    plt.ylabel("PV-Leistung (W)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=140, facecolor="white")
    plt.close()


def save_model_artifacts(model, feature_columns, metrics, observed_peak_w):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "model.json"
    features_path = MODEL_DIR / "features.json"
    metrics_path = MODEL_DIR / "metrics.json"

    model.save_model(model_path)
    with features_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "feature_columns": feature_columns,
                "target_column": TARGET_COLUMN,
                "use_neighbor_features": USE_NEIGHBOR_FEATURES,
                "use_neighbor_deltas": USE_NEIGHBOR_DELTAS,
                "neighbor_offsets": NEIGHBOR_OFFSETS,
                "neighbor_base_columns": NEIGHBOR_BASE_COLUMNS,
                "safe_prediction_factor": SAFE_PREDICTION_FACTOR,
                "model_objective": XGB_OBJECTIVE,
                "observed_peak_w": observed_peak_w,
            },
            file,
            indent=2,
        )
        file.write("\n")

    with metrics_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "trained_at": datetime.now().isoformat(timespec="seconds"),
                "model": model.__class__.__name__,
                "objective": XGB_OBJECTIVE,
                "model_params": MODEL_PARAMS,
                "metrics": json_safe(metrics),
            },
            file,
            indent=2,
        )
        file.write("\n")
    return model_path


def json_safe(value):
    if isinstance(value, dict):
        return {
            key: json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def main():
    rows, base_feature_columns, neighbor_columns = load_dataset_rows()
    data = build_feature_matrix(rows, base_feature_columns, neighbor_columns)
    splits = split_dataset(data)
    observed_peak_w = max(float(row[TARGET_COLUMN]) for row in rows)

    print(f"Basisfeatures: {len(base_feature_columns)}")
    print(f"Nachbarfeatures aktiv: {USE_NEIGHBOR_FEATURES}")
    print(f"Neighbor-Deltas aktiv: {USE_NEIGHBOR_DELTAS}")
    print(f"Neighbor-Basisfeatures: {len(neighbor_columns)}")
    print(f"Gesamtfeatures: {len(data['feature_columns'])}")

    model = create_model()
    print(f"ML-Modell: {model.__class__.__name__}")
    print(f"Parameter: {MODEL_PARAMS}")
    model.fit(splits["train"]["features"], splits["train"]["target"])

    metrics = {}
    predictions_by_split = {}
    safe_predictions_by_split = {}
    for split_name, split_data in splits.items():
        predictions = predict_split(model, split_data)
        safe_values = safe_predictions(predictions)
        predictions_by_split[split_name] = predictions
        safe_predictions_by_split[split_name] = safe_values
        split_metrics = evaluate_split(split_data, predictions)
        safe_metrics = evaluate_split(split_data, safe_values)
        metrics[split_name] = {
            "expected": split_metrics,
            "safe": safe_metrics,
        }
        all_metrics = split_metrics["all"]
        safe_all_metrics = safe_metrics["all"]
        daylight_metrics = split_metrics["daylight"]
        active_metrics = split_metrics["active_pv"]
        print(
            f"{split_name}: "
            f"All MAE={all_metrics['mae_w']:.2f} W, RMSE={all_metrics['rmse_w']:.2f} W | "
            f"Over={all_metrics['over_mae_w']:.2f} W, Under={all_metrics['under_mae_w']:.2f} W | "
            f"Safe MAE={safe_all_metrics['mae_w']:.2f} W, "
            f"Safe Over={safe_all_metrics['over_mae_w']:.2f} W, "
            f"Safe Under={safe_all_metrics['under_mae_w']:.2f} W | "
            f"Day MAE={daylight_metrics['mae_w']:.2f} W | "
            f"Active MAE={active_metrics['mae_w']:.2f} W"
        )

    test_predictions = predictions_by_split["test"]
    test_safe_predictions = safe_predictions_by_split["test"]
    plot_test_predictions(
        splits["test"]["timestamps"],
        splits["test"]["target"],
        test_predictions,
        test_safe_predictions,
    )
    importance_path = (
        save_feature_importance(model, data["feature_columns"])
        if SAVE_FEATURE_IMPORTANCE
        else None
    )
    predictions_path = save_test_predictions(splits["test"], test_predictions, test_safe_predictions)
    model_path = save_model_artifacts(model, data["feature_columns"], metrics, observed_peak_w)
    print(f"Modell gespeichert: {model_path}")
    print(f"Plots gespeichert: {PLOTS_DIR}")
    if importance_path:
        print(f"Feature Importance: {importance_path}")
    print(f"Test-Prognosen: {predictions_path}")


if __name__ == "__main__":
    main()
