from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, dict[str, float | int]] | None:
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry_id)
    if coordinator is None:
        return None

    data = coordinator.data
    if data is None or not data.forecast_points:
        return None

    wh_hours: dict[str, float] = {}
    hour_bucket: int | None = None
    hour_wh: float = 0.0

    for point in data.forecast_points:
        ts = dt_util.as_local(point.timestamp)
        bucket = ts.hour

        if hour_bucket is not None and bucket != hour_bucket:
            wh_hours[ts.replace(minute=0, second=0, microsecond=0).isoformat()] = round(hour_wh, 1)
            hour_wh = 0.0

        hour_bucket = bucket
        hour_wh += point.pv_power_w * 0.25

    if hour_bucket is not None and hour_wh > 0:
        last_ts = dt_util.as_local(data.forecast_points[-1].timestamp)
        wh_hours[last_ts.replace(minute=0, second=0, microsecond=0).isoformat()] = round(hour_wh, 1)

    return {"wh_hours": wh_hours}
