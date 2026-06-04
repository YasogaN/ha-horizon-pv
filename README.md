# PV Forecast Planner

<p align="center">
  <img src="assets/logo.png" alt="PV Forecast Planner logo" width="300">
</p>

Home Assistant custom integration that uses a trained XGBoost PV model, fetches Open-Meteo forecast data, and exposes `sensor.pv_forecast_power`.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=wolpa29&repository=homeassistant-pv-forecast-planner&category=integration)

The sensor state is the predicted PV power for the current 15-minute slot in watts; the full future forecast is available in the `forecast` attribute. The `forecast` attribute is replaced whenever a new forecast is calculated.

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

Setup asks for the model directory, latitude, longitude, timezone, panel azimuth, panel tilt, forecast days, and secondary Open-Meteo model such as `icon_eu`.

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

## Files

`__init__.py` sets up the integration and registers the update service.

`config_flow.py` defines the UI setup fields.

`coordinator.py` runs forecast updates.

`sensor.py` exposes `sensor.pv_forecast_power`.

`services.yaml` defines `pv_forecast_planner.update_forecast`.

`brand/` contains the Home Assistant icon and logo files.

`pv/weather.py` fetches Open-Meteo data.

`pv/model.py` loads the XGBoost model and metadata.

`pv/physical_model.py` calculates solar helper values.

`pv/features.py` builds the model feature matrix.

`pv/forecast.py` combines weather, features, and model prediction.

## License

MIT License. See `LICENSE`.
