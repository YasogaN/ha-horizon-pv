# PV Forecast Planner

<p align="center">
  <img src="assets/logo.png" alt="PV Forecast Planner logo" width="300">
</p>

Home Assistant custom integration that reads a trained XGBoost JSON model with a pure Python predictor, fetches Open-Meteo forecast data, and exposes PV forecast sensors.

Optional tools for SunnyPortal scraping, generic PV measurement CSVs, Open-Meteo training data, dataset creation, and model training are in `tools/`.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=wolpa29&repository=homeassistant-pv-forecast-planner&category=integration)

The main sensor state is the predicted PV power for now in watts. A second sensor exposes the current safe forecast power. Each sensor has its own compact 15-minute `forecast` attribute and it is replaced whenever a new forecast is calculated.
Between forecast updates, the sensor states are refreshed locally and linearly interpolated from the stored forecast curve.
The last successful forecast is cached in `/config/pv_forecast_planner/` and restored after a restart or integration update if the weather API is temporarily unavailable.

Entities:

```text
sensor.pv_forecast_planner_forecast_power
sensor.pv_forecast_planner_safe_forecast_power
sensor.pv_forecast_planner_load_plan
```

Forecast attribute format:

```text
sensor.pv_forecast_planner_forecast_power
forecast_format: ["datetime", "pv_power_w"]
forecast:
  - ["2026-06-04T12:30:00", 6394.9]

sensor.pv_forecast_planner_safe_forecast_power
forecast_format: ["datetime", "safe_pv_power_w"]
forecast:
  - ["2026-06-04T12:30:00", 5755.4]
```

## Installation

Install with HACS as a custom repository, or copy this folder to:

```text
/config/custom_components/pv_forecast_planner/
```

Restart Home Assistant and add the integration from:

```text
Settings -> Devices & services -> Add integration -> PV Forecast Planner
```

## Model

Place your trained model files outside `custom_components`, for example:

```text
/config/pv_forecast_planner/models/default/model.json
/config/pv_forecast_planner/models/default/features.json
```

Use this path during setup:

```text
/config/pv_forecast_planner/models/default
```

## Configuration

Setup asks for the model directory, latitude, longitude, timezone, panel azimuth, panel tilt, forecast days, safe forecast factor, and secondary Open-Meteo model such as `icon_eu`.

After setup, change these values from the integration options.

## Automation

Call this service from an automation to calculate or replace the forecast:

```yaml
alias: Update PV forecast every morning
trigger:
  - platform: time
    at: "06:00:00"
action:
  - service: pv_forecast_planner.update_forecast
mode: single
```

Temporary Open-Meteo gateway or timeout errors are retried automatically before the update fails.

For basic load planning, copy `examples/loads.yaml` to `/config/pv_forecast_planner/loads.yaml`.
The planner uses the stored safe forecast from now until the last forecast point.
Each load needs `total_minutes`, `min_run_minutes`, `power_w`, `earliest_start`, and `latest_end`.
Loads may be split into multiple blocks, but each block must be at least `min_run_minutes` long.
Directly adjacent blocks of the same load are merged, so there are no unnecessary off/on events.
Optional `max_starts` can be used to limit the number of separate runs.
`sensor.pv_forecast_planner_load_plan` exposes planned load blocks in `plan` and concrete switching events in `events`.
Each event contains `time`, `device`, `action`, and optional `entity_id` or `script`.

```yaml
action:
  - service: pv_forecast_planner.update_forecast
  - service: pv_forecast_planner.update_load_plan
```

## Dashboard

To use the attributes of the forecast data you can use an apexchart which displays the current PV generation, forecast curves, and planned load blocks:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: PV Forecast
graph_span: 24h
span:
  start: day
now:
  show: false
  label: now
apex_config:
  chart:
    height: 320
  stroke:
    curve: smooth
  yaxis:
    min: 0
series:
  - entity: sensor.sn_3015651602_pv_power
    name: Actual PV
    type: line
    color: "#f5c542"
    stroke_width: 2
    extend_to: false
    group_by:
      duration: 15min
      func: avg
  - entity: sensor.pv_forecast_planner_forecast_power
    name: Forecast
    type: line
    color: "#36a3ff"
    stroke_width: 2
    data_generator: |
      return entity.attributes.forecast.map((row) => {
        return [new Date(row[0]).getTime(), row[1]];
      });
  - entity: sensor.pv_forecast_planner_safe_forecast_power
    name: Safe Forecast
    type: line
    color: "#7fbfff"
    stroke_width: 2
    data_generator: |
      return entity.attributes.forecast.map((row) => {
        return [new Date(row[0]).getTime(), row[1]];
      });
  - entity: sensor.pv_forecast_planner_load_plan
    name: Planned Load
    type: area
    color: "#ff9f43"
    opacity: 0.28
    stroke_width: 0
    curve: stepline
    data_generator: |
      return (entity.attributes.planned_load || []).map((row) => {
        return [new Date(row[0]).getTime(), row[1]];
      });

```

## Logging

Enable debug logs while testing:

```yaml
logger:
  logs:
    custom_components.pv_forecast_planner: debug
```

## Local smoke test

Optional local test setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 custom_components/pv_forecast_planner/tests.py
```

The integration does not require XGBoost to be installed in Home Assistant.
For local experiments, `PvForecastModel(..., backend="xgboost")` can use the optional XGBoost package.

## Files

`__init__.py` sets up the integration and registers the update service.

`config_flow.py` defines the UI setup fields.

`coordinator.py` runs forecast updates.

`sensor.py` exposes the forecast power and safe forecast power sensors.

`services.yaml` defines the forecast, load plan, and due event runner services.

Root `brand/` contains the HACS repository brand icons.

`custom_components/pv_forecast_planner/brand/` contains the Home Assistant brand icons.

`home-assistant-brands/` contains files prepared for a PR to `home-assistant/brands`.

`pv/weather.py` fetches Open-Meteo data.

`pv/model.py` loads the XGBoost JSON model and predicts with pure Python.

`pv/physical_model.py` calculates solar helper values.

`pv/features.py` builds the model feature matrix.

`pv/forecast.py` combines weather, features, and model prediction.

## Load Planner

Create this file:

```text
/config/pv_forecast_planner/loads.yaml
```

Minimal example:

```yaml
base_load_w: 500

loads:
  - name: Dishwasher
    entity_id: switch.dishwasher
    turn_on_script: script.start_dishwasher
    turn_off_script: script.stop_dishwasher
    power_w: 1200
    total_minutes: 90
    min_run_minutes: 90
    earliest_start: "09:00"
    latest_end: "18:00"
    priority: 1

  - name: EV charger
    turn_on_script: script.ev_charger_on
    turn_off_script: script.ev_charger_off
    power_w: 3000
    total_minutes: 120
    min_run_minutes: 60
    earliest_start: "10:00"
    latest_end: "17:00"
    priority: 2
```

Required fields per load: `name`, `power_w`, `total_minutes`, `min_run_minutes`, `earliest_start`, `latest_end`.
Optional fields: `priority`, `entity_id`, `turn_on_script`, `turn_off_script`, `max_starts`.
`entity_id` is optional, so script-only loads are valid.

Run forecast and load planning:

```yaml
action:
  - service: pv_forecast_planner.update_forecast
  - service: pv_forecast_planner.update_load_plan
```

The planner uses the safe PV forecast, subtracts `base_load_w`, and places the loads where they fit best under the safe forecast curve.
It first minimizes forecast overflow, then prefers the block with the highest remaining safety margin.
The output is available on `sensor.pv_forecast_planner_load_plan`:

```text
plan: planned load blocks
events: turn_on / turn_off events with time, device, entity_id and optional script
planned_load: 15-minute load curve for charts
```

The dashboard example above shows `planned_load` as orange load blocks together with actual PV, forecast, and safe forecast.

For automation, let the integration execute due events. If an event has a script, the script is called. Otherwise the configured `entity_id` is switched directly. Events without script and without `entity_id` are skipped and logged.

Example morning plan update:

```yaml
alias: PV forecast and load plan
trigger:
  - platform: time
    at: "06:00:00"
action:
  - service: pv_forecast_planner.update_forecast
  - service: pv_forecast_planner.update_load_plan
mode: single
```

Example event runner:

```yaml
alias: Run PV load plan events
trigger:
  - platform: time_pattern
    minutes: "/1"
action:
  - service: pv_forecast_planner.run_due_load_events
mode: single
```

## License

MIT License. See `LICENSE`.
