"""Sensor platform for PV Forecast Planner."""

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
from .coordinator import PvForecastCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PV forecast sensors."""
    coordinator: PvForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PvForecastPowerSensor(coordinator, entry),
            PvSafeForecastPowerSensor(coordinator, entry),
        ]
    )


class PvForecastPowerSensor(CoordinatorEntity[PvForecastCoordinator], SensorEntity):
    """Current 15-minute PV forecast power sensor."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_has_entity_name = True
    _attr_name = "Forecast power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PvForecastCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_forecast_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "PV Forecast Planner",
        }

    @property
    def native_value(self) -> float | None:
        """Return the current forecast power in watts."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.current_power_w, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return forecast metadata and future time series."""
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "generated_at": data.generated_at.isoformat(),
            "current_slot": data.current_slot.isoformat(),
            "total_energy_kwh": round(data.total_energy_kwh, 3),
            "interval_minutes": 15,
            "forecast_format": [
                "datetime",
                "pv_power_w",
            ],
            "forecast": [
                [
                    point.timestamp.isoformat(),
                    round(point.pv_power_w, 1),
                ]
                for point in data.forecast_points
            ],
        }


class PvSafeForecastPowerSensor(CoordinatorEntity[PvForecastCoordinator], SensorEntity):
    """Current 15-minute safe PV forecast power sensor."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_has_entity_name = True
    _attr_name = "Safe forecast power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PvForecastCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_safe_forecast_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "PV Forecast Planner",
        }

    @property
    def native_value(self) -> float | None:
        """Return the current safe forecast power in watts."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.safe_current_power_w, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return safe forecast metadata."""
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "generated_at": data.generated_at.isoformat(),
            "current_slot": data.current_slot.isoformat(),
            "total_energy_kwh": round(data.safe_total_energy_kwh, 3),
            "interval_minutes": 15,
            "forecast_format": [
                "datetime",
                "safe_pv_power_w",
            ],
            "forecast": [
                [
                    point.timestamp.isoformat(),
                    round(point.safe_pv_power_w, 1),
                ]
                for point in data.forecast_points
            ],
        }
