from __future__ import annotations

from typing import Any


class OnlineSGDRegressor:
    def __init__(self, n_features: int, learning_rate: float = 0.01):
        self.coeffs = [0.0] * n_features
        self.intercept = 0.0
        self.lr = learning_rate
        self.n_features = n_features

    def partial_fit(self, X: list[list[float]], y: list[float]) -> None:
        for features, target in zip(X, y):
            prediction = self._dot(features)
            error = target - prediction
            self.intercept += self.lr * error
            for i in range(self.n_features):
                self.coeffs[i] += self.lr * error * features[i]

    def predict(self, features: list[float]) -> float:
        return max(0.0, self._dot(features))

    def predict_batch(self, X: list[list[float]]) -> list[float]:
        return [self.predict(row) for row in X]

    def _dot(self, features: list[float]) -> float:
        result = self.intercept
        for i in range(self.n_features):
            result += self.coeffs[i] * features[i]
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "coeffs": self.coeffs,
            "intercept": self.intercept,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OnlineSGDRegressor:
        n = len(data["coeffs"])
        obj = cls(n)
        obj.coeffs = list(data["coeffs"])
        obj.intercept = float(data["intercept"])
        return obj
