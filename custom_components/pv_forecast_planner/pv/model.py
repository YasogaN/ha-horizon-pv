from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from time import perf_counter
from typing import Any

_LOGGER = logging.getLogger(__name__)
BACKEND_PYTHON = "python"
BACKEND_XGBOOST = "xgboost"
SUPPORTED_BACKENDS = {BACKEND_PYTHON, BACKEND_XGBOOST}


class PvForecastModel:
    def __init__(self, model_dir: str | Path, *, backend: str = BACKEND_PYTHON):
        self.model_dir = Path(model_dir)
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"Unsupported model backend: {backend}")
        self.backend = backend
        self.model: PurePythonXGBoostModel | XGBoostRuntimeModel | None = None
        self.metadata: dict[str, Any] | None = None

    def load(self) -> None:
        """Load model.json and features.json from the configured model directory."""
        _LOGGER.info(
            "Loading PV forecast model from %s with backend=%s",
            self.model_dir,
            self.backend,
        )
        started = perf_counter()
        self.load_metadata()
        self.load_model()
        _LOGGER.info(
            "PV forecast model loaded: backend=%s, features=%s, observed_peak_w=%s, "
            "safe_factor=%s, duration_s=%.2f",
            self.backend,
            len(self.feature_columns),
            self.observed_peak_w,
            self.safe_prediction_factor,
            perf_counter() - started,
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

        if self.backend == BACKEND_XGBOOST:
            self.model = XGBoostRuntimeModel.from_file(model_path)
            _LOGGER.debug("Loaded XGBoost runtime model from %s", model_path)
            return

        self.model = PurePythonXGBoostModel.from_file(model_path)
        _LOGGER.debug("Loaded pure Python model from %s", model_path)

    def predict(self, feature_matrix: list[list[float]]) -> list[float]:
        """Predict PV power in watts for the given feature matrix."""
        if self.model is None or self.metadata is None:
            self.load()

        _LOGGER.debug(
            "Running model prediction for %s rows with backend=%s",
            len(feature_matrix),
            self.backend,
        )
        started = perf_counter()
        predictions = self.model.predict(feature_matrix)
        _LOGGER.info(
            "Model prediction finished: backend=%s, rows=%s, duration_s=%.2f",
            self.backend,
            len(feature_matrix),
            perf_counter() - started,
        )
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


class PurePythonXGBoostModel:
    """Small XGBoost JSON predictor for gbtree regression models."""

    def __init__(self, base_score: float, trees: list[dict[str, list[Any]]]) -> None:
        self.base_score = base_score
        self.trees = trees

    @classmethod
    def from_file(cls, model_path: str | Path) -> PurePythonXGBoostModel:
        """Load a supported XGBoost JSON model."""
        with Path(model_path).open("r", encoding="utf-8") as file:
            model = json.load(file)

        learner = model["learner"]
        objective = learner["objective"]["name"]
        if objective != "reg:squarederror":
            raise ValueError(f"Unsupported XGBoost objective: {objective}")

        booster = learner["gradient_booster"]
        if booster["name"] != "gbtree":
            raise ValueError(f"Unsupported XGBoost booster: {booster['name']}")

        base_score = _parse_base_score(learner["learner_model_param"]["base_score"])
        trees = booster["model"]["trees"]
        for tree in trees:
            if any(split_type != 0 for split_type in tree.get("split_type", [])):
                raise ValueError("Categorical XGBoost splits are not supported")
        return cls(base_score, trees)

    def predict(self, feature_matrix: list[list[float]]) -> list[float]:
        """Predict one value per feature row."""
        return [self.predict_row(row) for row in feature_matrix]

    def predict_row(self, features: list[float]) -> float:
        """Predict one feature row."""
        prediction = self.base_score
        for tree in self.trees:
            prediction += _predict_tree(tree, features)
        return prediction


class XGBoostRuntimeModel:
    """Thin wrapper around the optional xgboost package for local use."""

    def __init__(self, model: Any, dmatrix_cls: Any) -> None:
        self.model = model
        self.dmatrix_cls = dmatrix_cls

    @classmethod
    def from_file(cls, model_path: str | Path) -> XGBoostRuntimeModel:
        """Load an XGBoost model with the optional xgboost package."""
        try:
            from xgboost import Booster, DMatrix
        except ImportError as err:
            raise ImportError(
                "The xgboost backend requires the optional xgboost package. "
                "Use backend='python' or install xgboost locally."
            ) from err

        model = Booster()
        model.load_model(model_path)
        return cls(model, DMatrix)

    def predict(self, feature_matrix: list[list[float]]) -> list[float]:
        """Predict one value per feature row."""
        return [float(value) for value in self.model.predict(self.dmatrix_cls(feature_matrix))]


def _predict_tree(tree: dict[str, list[Any]], features: list[float]) -> float:
    """Walk one XGBoost tree and return the leaf value."""
    left_children = tree["left_children"]
    right_children = tree["right_children"]
    default_left = tree["default_left"]
    split_indices = tree["split_indices"]
    split_conditions = tree["split_conditions"]

    node = 0
    while left_children[node] != -1:
        feature_index = split_indices[node]
        split_value = split_conditions[node]
        feature_value = features[feature_index]

        if feature_value is None or math.isnan(feature_value):
            go_left = bool(default_left[node])
        else:
            go_left = feature_value < split_value

        node = left_children[node] if go_left else right_children[node]

    return float(split_conditions[node])


def _parse_base_score(value: str) -> float:
    """Parse XGBoost's JSON base score field."""
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return float(text)
