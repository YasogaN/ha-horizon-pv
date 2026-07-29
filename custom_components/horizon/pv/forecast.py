from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from time import perf_counter

from .cold_start import ColdStartPredictor
from .features import FEATURE_COLUMNS, build_feature_matrix, build_feature_rows
from .predictor import HorizonPredictor
from .sgd import OnlineSGDRegressor
from .standardizer import OnlineStandardizer
from .weather import fetch_open_meteo_forecast

INTERVAL_MINUTES = 15
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PvForecastPoint:
    timestamp: datetime
    pv_power_w: float

    @property
    def pv_energy_kwh(self) -> float:
        return self.pv_power_w * INTERVAL_MINUTES / 60 / 1000


@dataclass(frozen=True)
class PvForecastResult:
    generated_at: datetime
    current_slot: datetime
    current_power_w: float
    total_energy_kwh: float
    forecast_points: tuple[PvForecastPoint, ...]


@dataclass(frozen=True)
class PvForecastConfig:
    latitude: float
    longitude: float
    timezone: str
    panel_azimuth_deg: float
    panel_tilt_deg: float
    forecast_days: int


def create_pv_forecast(
    config: PvForecastConfig,
    predictor: HorizonPredictor,
    *,
    now: datetime,
) -> PvForecastResult:
    started = perf_counter()
    current_slot = floor_to_interval(now.replace(tzinfo=None), INTERVAL_MINUTES)

    weather = fetch_open_meteo_forecast(
        latitude=config.latitude,
        longitude=config.longitude,
        timezone=config.timezone,
        forecast_days=config.forecast_days,
    )

    rows = build_feature_rows(
        weather,
        observed_peak_w=predictor.observed_peak_w,
        latitude=config.latitude,
        longitude=config.longitude,
        timezone=config.timezone,
        panel_azimuth_deg=config.panel_azimuth_deg,
        panel_tilt_deg=config.panel_tilt_deg,
    )

    X_raw = build_feature_matrix(rows, FEATURE_COLUMNS)

    clear_sky_values = [r["clear_sky_panel_irradiance"] for r in rows]
    cloud_cover_values = [r["cloud_cover"] for r in rows]

    predictions = predictor.predict_batch(
        X_raw, clear_sky_values, cloud_cover_values
    )

    points = tuple(
        PvForecastPoint(row["_timestamp"], pred)
        for row, pred in zip(rows, predictions)
        if row["_timestamp"] >= current_slot
    )

    if not points:
        raise ValueError("No forecast points available for the current slot")

    current_point = min(
        points,
        key=lambda p: abs(p.timestamp - current_slot),
    )

    result = PvForecastResult(
        generated_at=now,
        current_slot=current_point.timestamp,
        current_power_w=current_point.pv_power_w,
        total_energy_kwh=sum(p.pv_energy_kwh for p in points),
        forecast_points=points,
    )

    _LOGGER.info(
        "Forecast created: mode=%s, current_w=%.1f, total_kwh=%.3f, duration_s=%.2f",
        predictor.mode,
        result.current_power_w,
        result.total_energy_kwh,
        perf_counter() - started,
    )
    return result


def floor_to_interval(value: datetime, interval_minutes: int) -> datetime:
    minute = value.minute - (value.minute % interval_minutes)
    return value.replace(minute=minute, second=0, microsecond=0)
