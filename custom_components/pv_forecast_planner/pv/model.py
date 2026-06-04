from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any

_LOGGER = logging.getLogger(__name__)
VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"


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

        Booster = _import_booster()

        model = Booster()
        model.load_model(model_path)
        self.model = model
        _LOGGER.debug("Loaded XGBoost model from %s", model_path)

    def predict(self, feature_matrix: list[list[float]]) -> list[float]:
        """Predict PV power in watts for the given feature matrix."""
        if self.model is None or self.metadata is None:
            self.load()

        DMatrix = _import_dmatrix()

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


def _prepare_vendor_import() -> None:
    """Add bundled Python packages to sys.path if they are present."""
    if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
        sys.path.insert(0, str(VENDOR_DIR))
        _LOGGER.info("Using bundled Python packages from %s", VENDOR_DIR)


def _import_booster() -> Any:
    """Import XGBoost Booster from the runtime or bundled vendor package."""
    try:
        from xgboost import Booster

        return Booster
    except ImportError as first_error:
        _prepare_vendor_import()
        try:
            from xgboost import Booster

            return Booster
        except ImportError as second_error:
            raise ImportError(
                "Could not import xgboost. The integration tried the Home Assistant "
                "runtime and the bundled vendor package. Missing dependency: "
                f"{second_error}"
            ) from first_error


def _import_dmatrix() -> Any:
    """Import XGBoost DMatrix from the runtime or bundled vendor package."""
    try:
        from xgboost import DMatrix

        return DMatrix
    except ImportError as first_error:
        _prepare_vendor_import()
        try:
            from xgboost import DMatrix

            return DMatrix
        except ImportError as second_error:
            raise ImportError(
                "Could not import xgboost. The integration tried the Home Assistant "
                "runtime and the bundled vendor package. Missing dependency: "
                f"{second_error}"
            ) from first_error
