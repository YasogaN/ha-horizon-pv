from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import recorder
from homeassistant.util import dt as dt_util

from .sgd import OnlineSGDRegressor
from .standardizer import OnlineStandardizer

_LOGGER = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "clear_sky_panel_irradiance",
    "cloud_cover",
    "solar_elevation_deg",
    "hour_sin",
    "hour_cos",
    "shortwave_radiation",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
]

MODEL_STATE_PATH = Path("/config/horizon/model_state.json")
SCHEMA_VERSION = 1


class DailyLearner:
    def __init__(
        self,
        hass: HomeAssistant,
        sgd: OnlineSGDRegressor,
        standardizer: OnlineStandardizer,
        pv_sensor_entity: str,
        observed_peak_w: float,
    ):
        self.hass = hass
        self.sgd = sgd
        self.standardizer = standardizer
        self.pv_sensor_entity = pv_sensor_entity
        self.observed_peak_w = observed_peak_w
        self.training_days = 0
        self.last_training_date: str | None = None
        self.daily_errors: list[dict[str, Any]] = []

    async def async_train_on_yesterday(self) -> bool:
        yesterday = dt_util.now() - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

        if self.last_training_date == date_str:
            _LOGGER.info("Already trained on %s, skipping", date_str)
            return False

        yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = yesterday_start + timedelta(days=1)

        actuals = await self._query_recorder(
            self.pv_sensor_entity, yesterday_start, today_start
        )
        if not actuals:
            _LOGGER.warning("No recorder data for %s, skipping training", date_str)
            return False

        _LOGGER.info(
            "Training on %s: %s recorder samples",
            date_str,
            len(actuals),
        )
        return True

    async def _query_recorder(
        self,
        entity_id: str,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, float]]:
        try:
            instance = recorder.get_instance(self.hass)
            metadata = await instance.async_add_executor_job(
                recorder.get_metadata, self.hass, entity_id
            )
            if not metadata:
                _LOGGER.warning("No recorder metadata for %s", entity_id)
                return []

            metadata_id, _ = next(iter(metadata.items()))

            def query():
                import sqlalchemy as sa
                from homeassistant.components.recorder.models import (
                    StatisticsShortTerm,
                )

                session = instance.get_session()
                stmt = (
                    sa.select(
                        StatisticsShortTerm.start_ts,
                        StatisticsShortTerm.mean,
                    )
                    .where(
                        StatisticsShortTerm.metadata_id == metadata_id,
                        StatisticsShortTerm.start_ts >= start.timestamp(),
                        StatisticsShortTerm.start_ts < end.timestamp(),
                    )
                    .order_by(StatisticsShortTerm.start_ts)
                )
                return list(session.execute(stmt))

            rows = await instance.async_add_executor_job(query)
            return [
                (datetime.fromtimestamp(row.start_ts), float(row.mean))
                for row in rows
            ]
        except Exception as err:
            _LOGGER.exception("Failed to query recorder: %s", err)
            return []

    def load_state(self) -> None:
        path = Path(MODEL_STATE_PATH)
        if not path.exists():
            _LOGGER.info("No model state file at %s, starting fresh", path)
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.sgd = OnlineSGDRegressor.from_dict(data)
            self.standardizer = OnlineStandardizer.from_dict(data.get("feature_stats", {}))
            self.training_days = data.get("training_days", 0)
            self.last_training_date = data.get("last_training_date")
            self.observed_peak_w = data.get("physics_observed_peak_w", self.observed_peak_w)
            _LOGGER.info(
                "Loaded model state: training_days=%s, last_date=%s",
                self.training_days,
                self.last_training_date,
            )
        except Exception as err:
            _LOGGER.exception("Failed to load model state: %s", err)

    def save_state(self) -> None:
        path = Path(MODEL_STATE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": SCHEMA_VERSION,
            "model_type": "online_sgd",
            "created_at": dt_util.now().isoformat(),
            "training_days": self.training_days,
            "last_training_date": self.last_training_date,
            "physics_observed_peak_w": self.observed_peak_w,
            "coeffs": self.sgd.coeffs,
            "intercept": self.sgd.intercept,
            "feature_columns": FEATURE_COLUMNS,
            "feature_stats": self.standardizer.to_dict(),
        }
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        temp_path.replace(path)
        _LOGGER.info("Saved model state: training_days=%s", self.training_days)
