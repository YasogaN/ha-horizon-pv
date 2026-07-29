from __future__ import annotations

from typing import Any


class OnlineStandardizer:
    def __init__(self, n_features: int):
        self.count = 0
        self.mean = [0.0] * n_features
        self.M2 = [0.0] * n_features
        self.n_features = n_features

    def partial_fit(self, X: list[list[float]]) -> None:
        for row in X:
            self.count += 1
            for i in range(self.n_features):
                delta = row[i] - self.mean[i]
                self.mean[i] += delta / self.count
                self.M2[i] += delta * (row[i] - self.mean[i])

    def transform(self, row: list[float]) -> list[float]:
        result = []
        for i in range(self.n_features):
            if self.count < 2:
                result.append(0.0)
            else:
                variance = self.M2[i] / (self.count - 1)
                std = variance ** 0.5
                result.append(0.0 if std < 1e-10 else (row[i] - self.mean[i]) / std)
        return result

    def transform_batch(self, X: list[list[float]]) -> list[list[float]]:
        return [self.transform(row) for row in X]

    @property
    def std(self) -> list[float]:
        if self.count < 2:
            return [1.0] * self.n_features
        return [
            ((m2 / (self.count - 1)) ** 0.5) if m2 > 0 else 1.0
            for m2 in self.M2
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean": self.mean,
            "std": self.std,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OnlineStandardizer:
        mean = list(data["mean"])
        n = len(mean)
        obj = cls(n)
        obj.count = data["count"]
        obj.mean = mean
        std = data.get("std", [1.0] * n)
        if obj.count > 1:
            obj.M2 = [s * s * (obj.count - 1) for s in std]
        return obj
