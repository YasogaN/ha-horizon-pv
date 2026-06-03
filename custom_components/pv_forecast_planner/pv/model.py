from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PvForecastModel:
    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir)
        self.model: Any | None = None
        self.metadata: dict[str, Any] | None = None

    def load(self) -> None:
        """Load model.json and features.json from the configured model directory."""
        self.load_metadata()
        self.load_model()

    def load_metadata(self) -> None:
        """Load features.json from the configured model directory."""
        features_path = self.model_dir / "features.json"
        if not features_path.exists():
            raise FileNotFoundError(f"Feature metadata missing in {self.model_dir}")

        with features_path.open("r", encoding="utf-8") as file:
            self.metadata = json.load(file)

    def load_model(self) -> None:
        """Load model.json from the configured model directory."""
        model_path = self.model_dir / "model.json"
        if not model_path.exists():
            raise FileNotFoundError(f"XGBoost model missing in {self.model_dir}")

        from xgboost import XGBRegressor

        model = XGBRegressor()
        model.load_model(model_path)
        self.model = model

    def predict(self, feature_matrix: list[list[float]]) -> list[float]:
        """Predict PV power in watts for the given feature matrix."""
        if self.model is None or self.metadata is None:
            self.load()

        predictions = self.model.predict(feature_matrix)
        return [max(0.0, float(value)) for value in predictions]

    @property
    def feature_columns(self) -> list[str]:
        if self.metadata is None:
            self.load_metadata()
        return self.metadata["feature_columns"]

    @property
    def observed_peak_w(self) -> float | None:
        if self.metadata is None:
            self.load_metadata()
        value = self.metadata.get("observed_peak_w")
        return None if value is None else float(value)

    @property
    def safe_prediction_factor(self) -> float:
        if self.metadata is None:
            self.load_metadata()
        return float(self.metadata.get("safe_prediction_factor", 0.9))
