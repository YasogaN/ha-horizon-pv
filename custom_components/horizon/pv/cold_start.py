from __future__ import annotations


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class ColdStartPredictor:
    def predict(
        self,
        clear_sky_panel_irradiance: float,
        cloud_cover: float,
        observed_peak_w: float,
    ) -> float:
        clear_sky_factor = clamp(clear_sky_panel_irradiance / 1000.0, 0.0, 1.15)
        cloud_factor = 1.0 - 0.6 * cloud_cover / 100.0
        return max(0.0, observed_peak_w * clear_sky_factor * cloud_factor)

    def predict_batch(
        self,
        clear_sky_values: list[float],
        cloud_cover_values: list[float],
        observed_peak_w: float,
    ) -> list[float]:
        return [
            self.predict(cs, cc, observed_peak_w)
            for cs, cc in zip(clear_sky_values, cloud_cover_values)
        ]
