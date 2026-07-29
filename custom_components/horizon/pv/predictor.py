from __future__ import annotations

from .cold_start import ColdStartPredictor
from .sgd import OnlineSGDRegressor
from .standardizer import OnlineStandardizer

COLD_START_THRESHOLD = 3
TRANSITION_THRESHOLD = 14
STEADY_STATE_SGD_WEIGHT = 0.8
STEADY_STATE_PHYSICS_WEIGHT = 0.2
TRANSITION_SGD_WEIGHT = 0.5
TRANSITION_PHYSICS_WEIGHT = 0.5


class HorizonPredictor:
    def __init__(
        self,
        sgd: OnlineSGDRegressor,
        standardizer: OnlineStandardizer,
        cold_start: ColdStartPredictor | None = None,
    ):
        self.sgd = sgd
        self.standardizer = standardizer
        self.cold_start = cold_start or ColdStartPredictor()
        self.training_days = 0
        self.observed_peak_w: float = 0.0

    @property
    def mode(self) -> str:
        if self.training_days < COLD_START_THRESHOLD:
            return "cold_start"
        elif self.training_days < TRANSITION_THRESHOLD:
            return "transition"
        else:
            return "steady_state"

    def predict(
        self,
        raw_features: list[float],
        clear_sky_panel_irradiance: float,
        cloud_cover: float,
    ) -> float:
        std_features = self.standardizer.transform(raw_features)
        sgd_prediction = self.sgd.predict(std_features)
        physics_prediction = self.cold_start.predict(
            clear_sky_panel_irradiance, cloud_cover, self.observed_peak_w
        )
        return self._blend(sgd_prediction, physics_prediction)

    def predict_batch(
        self,
        X_raw: list[list[float]],
        clear_sky_values: list[float],
        cloud_cover_values: list[float],
    ) -> list[float]:
        X_std = self.standardizer.transform_batch(X_raw)
        sgd_predictions = self.sgd.predict_batch(X_std)
        physics_predictions = self.cold_start.predict_batch(
            clear_sky_values, cloud_cover_values, self.observed_peak_w
        )
        return [
            self._blend(sgd_p, phys_p)
            for sgd_p, phys_p in zip(sgd_predictions, physics_predictions)
        ]

    def _blend(self, sgd_prediction: float, physics_prediction: float) -> float:
        if self.training_days < COLD_START_THRESHOLD:
            return physics_prediction
        elif self.training_days < TRANSITION_THRESHOLD:
            return (
                TRANSITION_SGD_WEIGHT * sgd_prediction
                + TRANSITION_PHYSICS_WEIGHT * physics_prediction
            )
        else:
            return (
                STEADY_STATE_SGD_WEIGHT * sgd_prediction
                + STEADY_STATE_PHYSICS_WEIGHT * physics_prediction
            )
