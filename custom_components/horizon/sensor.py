from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HorizonCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HorizonCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HorizonForecastPowerSensor(coordinator, entry),
            HorizonTrainingDaysSensor(coordinator, entry),
            HorizonModelDiagnosticsSensor(coordinator, entry),
        ]
    )


class HorizonForecastPowerSensor(
    CoordinatorEntity[HorizonCoordinator], SensorEntity
):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_has_entity_name = True
    _attr_name = "Forecast power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: HorizonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_forecast_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Horizon Solar Forecast",
        }

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.current_power_w, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "generated_at": data.generated_at.isoformat(),
            "current_slot": data.current_slot.isoformat(),
            "total_energy_kwh": round(data.total_energy_kwh, 3),
            "interval_minutes": 15,
            "forecast_format": ["datetime", "pv_power_w"],
            "forecast": [
                [point.timestamp.isoformat(), round(point.pv_power_w, 1)]
                for point in data.forecast_points
            ],
        }


class HorizonTrainingDaysSensor(
    CoordinatorEntity[HorizonCoordinator], SensorEntity
):
    _attr_has_entity_name = True
    _attr_name = "Training days"
    _attr_icon = "mdi:school"

    def __init__(self, coordinator: HorizonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_training_days"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Horizon Solar Forecast",
        }

    @property
    def native_value(self) -> int:
        return self.coordinator.predictor.training_days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        predictor = self.coordinator.predictor
        return {
            "last_training_date": self.coordinator.learner.last_training_date or "never",
            "prediction_mode": predictor.mode,
            "observed_peak_w": round(predictor.observed_peak_w, 1),
            "sgd_coefficients": predictor.sgd.coeffs,
            "sgd_intercept": round(predictor.sgd.intercept, 4),
        }


class HorizonModelDiagnosticsSensor(
    CoordinatorEntity[HorizonCoordinator], SensorEntity
):
    _attr_has_entity_name = True
    _attr_name = "Model diagnostics"
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: HorizonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_model_diagnostics"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Horizon Solar Forecast",
        }

    @property
    def native_value(self) -> str:
        return self.coordinator.predictor.mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.get_state()
        return {
            "training_days": state["training_days"],
            "last_training_date": state["last_training_date"] or "never",
            "prediction_mode": state["prediction_mode"],
            "physics_peak_w": round(state["physics_peak_w"], 1),
        }
