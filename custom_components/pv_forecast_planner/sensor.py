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
            PvLoadPlanSensor(coordinator, entry),
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


class PvLoadPlanSensor(CoordinatorEntity[PvForecastCoordinator], SensorEntity):
    """Basic PV load plan sensor."""

    _attr_has_entity_name = True
    _attr_name = "Load plan"

    def __init__(self, coordinator: PvForecastCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_load_plan"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "PV Forecast Planner",
        }

    @property
    def native_value(self) -> str:
        """Return the next planned load event."""
        plan = self.coordinator.load_plan
        if plan is None or plan.next_event is None:
            return "none"
        return f"{plan.next_event.device} {plan.next_event.action}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return load plan data."""
        plan = self.coordinator.load_plan
        if plan is None:
            return {}
        next_load = plan.next_load
        next_event = plan.next_event
        return {
            "generated_at": plan.generated_at.isoformat(),
            "forecast_start": plan.forecast_start.isoformat(),
            "forecast_end": plan.forecast_end.isoformat(),
            "base_load_w": round(plan.base_load_w, 1),
            "loads_planned": len(plan.planned_loads),
            "next_load": None if next_load is None else next_load.name,
            "next_start": None if next_load is None else next_load.start.isoformat(),
            "next_end": None if next_load is None else next_load.end.isoformat(),
            "next_event": None if next_event is None else next_event.action,
            "next_event_time": None if next_event is None else next_event.time.isoformat(),
            "next_event_device": None if next_event is None else next_event.device,
            "next_event_entity_id": None if next_event is None else next_event.entity_id,
            "next_event_script": None if next_event is None else next_event.script,
            "plan": [
                {
                    "name": load.name,
                    "entity_id": load.entity_id,
                    "turn_on_script": load.turn_on_script,
                    "turn_off_script": load.turn_off_script,
                    "start": load.start.isoformat(),
                    "end": load.end.isoformat(),
                    "power_w": round(load.power_w, 1),
                    "duration_minutes": load.duration_minutes,
                    "total_minutes": load.total_minutes,
                    "min_run_minutes": load.min_run_minutes,
                    "energy_kwh": round(load.energy_kwh, 3),
                }
                for load in plan.planned_loads
            ],
            "events": [
                {
                    "time": event.time.isoformat(),
                    "device": event.device,
                    "action": event.action,
                    "entity_id": event.entity_id,
                    "script": event.script,
                }
                for event in plan.events
            ],
            "planned_load_format": ["datetime", "planned_load_w"],
            "planned_load": [
                [timestamp.isoformat(), round(power_w, 1)]
                for timestamp, power_w in plan.planned_load_curve
            ],
        }
