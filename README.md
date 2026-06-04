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

## Dashboard

To use the attributes of the forecast data you can use an apexchart which displays also the current pv generation:

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

`services.yaml` defines `pv_forecast_planner.update_forecast`.

Root `brand/` contains the HACS repository brand icons.

`custom_components/pv_forecast_planner/brand/` contains the Home Assistant brand icons.

`home-assistant-brands/` contains files prepared for a PR to `home-assistant/brands`.

`pv/weather.py` fetches Open-Meteo data.

`pv/model.py` loads the XGBoost JSON model and predicts with pure Python.

`pv/physical_model.py` calculates solar helper values.

`pv/features.py` builds the model feature matrix.

`pv/forecast.py` combines weather, features, and model prediction.

## License

MIT License. See `LICENSE`.
