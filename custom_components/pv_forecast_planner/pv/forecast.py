"""PV forecast orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import logging
from pathlib import Path
from time import perf_counter

from .features import build_feature_matrix, build_feature_rows
from .model import PvForecastModel
from .weather import fetch_open_meteo_forecast

INTERVAL_MINUTES = 15
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PvForecastPoint:
    """One 15-minute PV forecast point."""

    timestamp: datetime
    pv_power_w: float
    safe_pv_power_w: float

    @property
    def pv_energy_kwh(self) -> float:
        """Return energy for this 15-minute point."""
        return self.pv_power_w * INTERVAL_MINUTES / 60 / 1000

    @property
    def safe_pv_energy_kwh(self) -> float:
        """Return safe energy for this 15-minute point."""
        return self.safe_pv_power_w * INTERVAL_MINUTES / 60 / 1000


@dataclass(frozen=True)
class PvForecastResult:
    """PV forecast result for Home Assistant."""

    generated_at: datetime
    current_slot: datetime
    current_power_w: float
    safe_current_power_w: float
    total_energy_kwh: float
    safe_total_energy_kwh: float
    forecast_points: tuple[PvForecastPoint, ...]


@dataclass(frozen=True)
class PvForecastConfig:
    """Runtime configuration for PV forecasting."""

    model_dir: str | Path
    latitude: float
    longitude: float
    timezone: str
    panel_azimuth_deg: float
    panel_tilt_deg: float
    forecast_days: int
    safe_forecast_factor: float | None
    secondary_forecast_model: str


def create_pv_forecast(
    config: PvForecastConfig,
    *,
    now: datetime,
) -> PvForecastResult:
    """Create a PV forecast from Open-Meteo data and the configured model."""
    started = perf_counter()
    current_slot = floor_to_interval(now.replace(tzinfo=None), INTERVAL_MINUTES)
    _LOGGER.info("Creating PV forecast for current_slot=%s", current_slot)
    model = get_model(str(Path(config.model_dir)))

    observed_peak_w = model.observed_peak_w
    if observed_peak_w is None:
        raise ValueError("features.json does not contain observed_peak_w")
    _LOGGER.info("Using observed_peak_w=%s from model metadata", observed_peak_w)

    primary_weather = fetch_open_meteo_forecast(
        latitude=config.latitude,
        longitude=config.longitude,
        timezone=config.timezone,
        forecast_days=config.forecast_days,
    )
    secondary_weather = fetch_open_meteo_forecast(
        latitude=config.latitude,
        longitude=config.longitude,
        timezone=config.timezone,
        forecast_days=config.forecast_days,
        model=config.secondary_forecast_model,
    )

    rows = build_feature_rows(
        primary_weather,
        secondary_weather,
        observed_peak_w=observed_peak_w,
        latitude=config.latitude,
        longitude=config.longitude,
        timezone=config.timezone,
        panel_azimuth_deg=config.panel_azimuth_deg,
        panel_tilt_deg=config.panel_tilt_deg,
    )
    if rows:
        _LOGGER.info(
            "Built PV feature rows: rows=%s, first=%s, last=%s",
            len(rows),
            rows[0]["_timestamp"],
            rows[-1]["_timestamp"],
        )
    else:
        _LOGGER.info("Built PV feature rows: rows=0")
    feature_matrix = build_feature_matrix(rows, model.feature_columns)
    _LOGGER.info(
        "Built PV feature matrix: rows=%s, columns=%s",
        len(feature_matrix),
        len(model.feature_columns),
    )
    predictions = model.predict(feature_matrix)
    safe_factor = (
        model.safe_prediction_factor
        if config.safe_forecast_factor is None
        else config.safe_forecast_factor
    )
    _LOGGER.info("Using safe_forecast_factor=%s", safe_factor)
    safe_predictions = [prediction * safe_factor for prediction in predictions]
    if predictions:
        _LOGGER.info(
            "PV model predictions created: rows=%s, min_w=%.1f, max_w=%.1f, "
            "first_w=%.1f, last_w=%.1f",
            len(predictions),
            min(predictions),
            max(predictions),
            predictions[0],
            predictions[-1],
        )

    points = tuple(
        PvForecastPoint(row["_timestamp"], prediction, safe_prediction)
        for row, prediction, safe_prediction in zip(rows, predictions, safe_predictions)
        if row["_timestamp"] >= current_slot
    )
    if not points:
        raise ValueError("No PV forecast points available for the current slot")
    _LOGGER.info(
        "Filtered PV forecast points: rows=%s, first=%s, last=%s",
        len(points),
        points[0].timestamp,
        points[-1].timestamp,
    )

    current_point = min(
        points,
        key=lambda point: abs(point.timestamp - current_slot),
    )

    result = PvForecastResult(
        generated_at=now,
        current_slot=current_point.timestamp,
        current_power_w=current_point.pv_power_w,
        safe_current_power_w=current_point.safe_pv_power_w,
        total_energy_kwh=sum(point.pv_energy_kwh for point in points),
        safe_total_energy_kwh=sum(point.safe_pv_energy_kwh for point in points),
        forecast_points=points,
    )
    _LOGGER.info(
        "PV forecast created: current_power_w=%.1f, safe_current_power_w=%.1f, "
        "total_energy_kwh=%.3f, safe_total_energy_kwh=%.3f, duration_s=%.2f",
        result.current_power_w,
        result.safe_current_power_w,
        result.total_energy_kwh,
        result.safe_total_energy_kwh,
        perf_counter() - started,
    )
    return result


def floor_to_interval(value: datetime, interval_minutes: int) -> datetime:
    """Floor a datetime to the previous interval boundary."""
    minute = value.minute - (value.minute % interval_minutes)
    return value.replace(minute=minute, second=0, microsecond=0)


@lru_cache(maxsize=4)
def get_model(model_dir: str, backend: str = "python") -> PvForecastModel:
    """Return a cached model wrapper for a model directory."""
    return PvForecastModel(model_dir, backend=backend)
