from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


class PvForecastModel:
    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir)
        self.model: Any | None = None
        self.metadata: dict[str, Any] | None = None

    def load(self) -> None:
        """Load model.json and features.json from the configured model directory."""
        _LOGGER.info("Loading PV forecast model from %s", self.model_dir)
        self.load_metadata()
        self.load_model()
        _LOGGER.info(
            "PV forecast model loaded: features=%s, observed_peak_w=%s, safe_factor=%s",
            len(self.feature_columns),
            self.observed_peak_w,
            self.safe_prediction_factor,
        )

    def load_metadata(self) -> None:
        """Load features.json from the configured model directory."""
        features_path = self.model_dir / "features.json"
        if not features_path.exists():
            raise FileNotFoundError(f"Feature metadata missing in {self.model_dir}")

        with features_path.open("r", encoding="utf-8") as file:
            self.metadata = json.load(file)
        _LOGGER.debug("Loaded PV forecast metadata from %s", features_path)

    def load_model(self) -> None:
        """Load model.json from the configured model directory."""
        model_path = self.model_dir / "model.json"
        if not model_path.exists():
            raise FileNotFoundError(f"XGBoost model missing in {self.model_dir}")

        from xgboost import Booster

        model = Booster()
        model.load_model(model_path)
        self.model = model
        _LOGGER.debug("Loaded XGBoost model from %s", model_path)

    def predict(self, feature_matrix: list[list[float]]) -> list[float]:
        """Predict PV power in watts for the given feature matrix."""
        if self.model is None or self.metadata is None:
            self.load()

        from xgboost import DMatrix

        _LOGGER.debug("Running PV model prediction for %s rows", len(feature_matrix))
        predictions = self.model.predict(DMatrix(feature_matrix))
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
