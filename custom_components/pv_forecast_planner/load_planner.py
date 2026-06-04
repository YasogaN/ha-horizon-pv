"""Basic load planner for PV Forecast Planner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import math
from pathlib import Path
from typing import Any

INTERVAL_MINUTES = 15


@dataclass(frozen=True)
class LoadConfig:
    name: str
    entity_id: str | None
    turn_on_script: str | None
    turn_off_script: str | None
    power_w: float
    total_minutes: int
    min_run_minutes: int
    max_starts: int
    earliest_start: time
    latest_end: time
    priority: int


@dataclass(frozen=True)
class PlannedLoad:
    name: str
    entity_id: str | None
    turn_on_script: str | None
    turn_off_script: str | None
    start: datetime
    end: datetime
    power_w: float
    duration_minutes: int
    total_minutes: int
    min_run_minutes: int
    energy_kwh: float


@dataclass(frozen=True)
class LoadPlanEvent:
    device: str
    action: str
    time: datetime
    entity_id: str | None
    script: str | None


@dataclass(frozen=True)
class LoadPlanResult:
    generated_at: datetime
    forecast_start: datetime
    forecast_end: datetime
    base_load_w: float
    planned_loads: tuple[PlannedLoad, ...]
    planned_load_curve: tuple[tuple[datetime, float], ...]

    @property
    def next_load(self) -> PlannedLoad | None:
        return self.planned_loads[0] if self.planned_loads else None

    @property
    def events(self) -> tuple[LoadPlanEvent, ...]:
        events: list[LoadPlanEvent] = []
        for load in self.planned_loads:
            events.append(
                LoadPlanEvent(
                    device=load.name,
                    action="turn_on",
                    time=load.start,
                    entity_id=load.entity_id,
                    script=load.turn_on_script,
                )
            )
            events.append(
                LoadPlanEvent(
                    device=load.name,
                    action="turn_off",
                    time=load.end,
                    entity_id=load.entity_id,
                    script=load.turn_off_script,
                )
            )
        return tuple(sorted(events, key=lambda item: item.time))

    @property
    def next_event(self) -> LoadPlanEvent | None:
        future_events = [event for event in self.events if event.time >= self.generated_at]
        return future_events[0] if future_events else None


def load_load_config(path: Path) -> tuple[float, list[LoadConfig]]:
    """Load basic load planning config from YAML."""
    from homeassistant.util.yaml.loader import load_yaml

    if not path.exists():
        raise FileNotFoundError(f"Load planner config missing: {path}")

    raw = load_yaml(str(path)) or {}
    base_load_w = float(raw.get("base_load_w", 0))
    loads = []
    for index, item in enumerate(raw.get("loads", [])):
        total_minutes = first_existing(item, "total_minutes", "duration_minutes")
        min_run_minutes = first_existing(
            item, "min_run_minutes", "min_duration_minutes", "min_runtime_minutes"
        )
        if total_minutes is None:
            raise ValueError(f"Missing total_minutes for load {item.get('name', index + 1)}")
        if min_run_minutes is None:
            raise ValueError(
                f"Missing min_run_minutes for load {item.get('name', index + 1)}"
            )

        loads.append(
            LoadConfig(
                name=str(item["name"]),
                entity_id=optional_str(first_existing(item, "entity_id", "entity")),
                turn_on_script=optional_str(
                    first_existing(item, "turn_on_script", "on_script", "start_script")
                ),
                turn_off_script=optional_str(
                    first_existing(item, "turn_off_script", "off_script", "stop_script")
                ),
                power_w=float(item["power_w"]),
                total_minutes=int(total_minutes),
                min_run_minutes=int(min_run_minutes),
                max_starts=int(
                    item.get(
                        "max_starts",
                        max(1, int(total_minutes) // max(1, int(min_run_minutes))),
                    )
                ),
                earliest_start=parse_time(
                    str(first_existing(item, "earliest_start", "earliest") or "00:00")
                ),
                latest_end=parse_time(
                    str(first_existing(item, "latest_end", "latest") or "23:59")
                ),
                priority=int(item.get("priority", index + 1)),
            )
        )
    if not loads:
        raise ValueError(f"No loads configured in {path}")
    return base_load_w, sorted(loads, key=lambda item: item.priority)


def create_load_plan(
    *,
    forecast_points: tuple[Any, ...],
    base_load_w: float,
    loads: list[LoadConfig],
    now: datetime,
) -> LoadPlanResult:
    """Create a simple greedy load plan using the safe PV forecast curve."""
    points = tuple(point for point in forecast_points if point.timestamp >= now)
    if not points:
        raise ValueError("No future forecast points available for load planning")

    planned_curve = [0.0 for _point in points]
    planned_loads: list[PlannedLoad] = []

    for load in loads:
        total_slots = max(1, math.ceil(load.total_minutes / INTERVAL_MINUTES))
        min_run_slots = max(1, math.ceil(load.min_run_minutes / INTERVAL_MINUTES))
        chunks = chunk_sizes(total_slots, min_run_slots, max(1, load.max_starts))
        if not chunks:
            continue

        blocked: set[int] = set()
        for duration_slots in chunks:
            best_start = find_best_start(
                points,
                planned_curve,
                base_load_w,
                load,
                duration_slots,
                blocked,
            )
            if best_start is None:
                continue

            for index in range(best_start, best_start + duration_slots):
                planned_curve[index] += load.power_w
                blocked.add(index)

            start = points[best_start].timestamp
            end = start + timedelta(minutes=duration_slots * INTERVAL_MINUTES)
            planned_loads.append(
                PlannedLoad(
                    name=load.name,
                    entity_id=load.entity_id,
                    turn_on_script=load.turn_on_script,
                    turn_off_script=load.turn_off_script,
                    start=start,
                    end=end,
                    power_w=load.power_w,
                    duration_minutes=duration_slots * INTERVAL_MINUTES,
                    total_minutes=load.total_minutes,
                    min_run_minutes=load.min_run_minutes,
                    energy_kwh=load.power_w * duration_slots * INTERVAL_MINUTES / 60 / 1000,
                )
            )

    planned_loads = merge_adjacent_loads(planned_loads)
    return LoadPlanResult(
        generated_at=now,
        forecast_start=points[0].timestamp,
        forecast_end=points[-1].timestamp,
        base_load_w=base_load_w,
        planned_loads=tuple(planned_loads),
        planned_load_curve=tuple(
            (point.timestamp, planned_load_w)
            for point, planned_load_w in zip(points, planned_curve)
        ),
    )


def find_best_start(
    points: tuple[Any, ...],
    planned_curve: list[float],
    base_load_w: float,
    load: LoadConfig,
    duration_slots: int,
    blocked: set[int],
) -> int | None:
    """Find the start slot with the safest fit below the forecast curve."""
    best_start = None
    best_score = None
    for start_index in range(0, len(points) - duration_slots + 1):
        if any(index in blocked for index in range(start_index, start_index + duration_slots)):
            continue

        block = points[start_index : start_index + duration_slots]
        if not is_allowed_window(block[0].timestamp, block[-1].timestamp, load):
            continue

        overflow_w = 0.0
        surplus_after_load_values = []
        for offset, point in enumerate(block):
            already_planned_w = planned_curve[start_index + offset]
            available_w = point.safe_pv_power_w - base_load_w - already_planned_w
            surplus_after_load_w = available_w - load.power_w
            overflow_w += max(0.0, -surplus_after_load_w)
            surplus_after_load_values.append(surplus_after_load_w)

        min_surplus_w = min(surplus_after_load_values)
        avg_surplus_w = sum(surplus_after_load_values) / len(surplus_after_load_values)
        score = (
            overflow_w,
            -min_surplus_w,
            -avg_surplus_w,
            block[0].timestamp,
        )
        if best_score is None or score < best_score:
            best_score = score
            best_start = start_index
    return best_start


def is_allowed_window(start: datetime, last_slot: datetime, load: LoadConfig) -> bool:
    """Return whether the load can run in its configured time window."""
    end = last_slot + timedelta(minutes=INTERVAL_MINUTES)
    if start.date() != end.date():
        return False
    return start.time() >= load.earliest_start and end.time() <= load.latest_end


def chunk_sizes(total_slots: int, min_run_slots: int, max_starts: int) -> list[int]:
    """Split total runtime into chunks that respect min run time and max starts."""
    if total_slots <= 0 or min_run_slots <= 0 or max_starts <= 0:
        return []
    if total_slots < min_run_slots:
        return []

    start_count = min(max_starts, total_slots // min_run_slots)
    if start_count <= 0:
        return []

    chunks = [min_run_slots for _index in range(start_count)]
    remaining = total_slots - (min_run_slots * start_count)
    index = 0
    while remaining > 0:
        chunks[index] += 1
        remaining -= 1
        index = (index + 1) % start_count
    return chunks


def merge_adjacent_loads(loads: list[PlannedLoad]) -> list[PlannedLoad]:
    """Merge directly adjacent blocks for the same load into one switching block."""
    merged: list[PlannedLoad] = []
    for load in sorted(loads, key=lambda item: (item.name, item.start)):
        if (
            merged
            and merged[-1].name == load.name
            and merged[-1].end == load.start
            and merged[-1].entity_id == load.entity_id
            and merged[-1].turn_on_script == load.turn_on_script
            and merged[-1].turn_off_script == load.turn_off_script
            and merged[-1].power_w == load.power_w
        ):
            previous = merged[-1]
            merged[-1] = PlannedLoad(
                name=previous.name,
                entity_id=previous.entity_id,
                turn_on_script=previous.turn_on_script,
                turn_off_script=previous.turn_off_script,
                start=previous.start,
                end=load.end,
                power_w=previous.power_w,
                duration_minutes=previous.duration_minutes + load.duration_minutes,
                total_minutes=previous.total_minutes,
                min_run_minutes=previous.min_run_minutes,
                energy_kwh=previous.energy_kwh + load.energy_kwh,
            )
            continue

        merged.append(load)

    return sorted(merged, key=lambda item: item.start)


def parse_time(value: str) -> time:
    """Parse HH:MM into a time."""
    return datetime.strptime(value, "%H:%M").time()


def first_existing(data: dict[str, Any], *keys: str) -> Any:
    """Return the first configured value from a dict."""
    for key in keys:
        if key in data:
            return data[key]
    return None


def optional_str(value: Any) -> str | None:
    """Return a stripped string or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
