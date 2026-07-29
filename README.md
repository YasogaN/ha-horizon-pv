<div align="center">
  <img src="assets/logo.png" alt="Horizon Solar Forecast logo" width="300">


[![GitHub License](https://img.shields.io/github/license/YasogaN/ha-horizon-pv?style=for-the-badge&color=blue)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/YasogaN/ha-horizon-pv?style=for-the-badge)](https://github.com/YasogaN/ha-horizon-pv/stargazers)
[![GitHub Watchers](https://img.shields.io/github/watchers/YasogaN/ha-horizon-pv?style=for-the-badge)](https://github.com/YasogaN/ha-horizon-pv/watchers)
[![GitHub Issues](https://img.shields.io/github/issues/YasogaN/ha-horizon-pv?style=for-the-badge)](https://github.com/YasogaN/ha-horizon-pv/issues)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5?style=for-the-badge)](https://hacs.xyz)

## Frameworks/Technologies

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?style=for-the-badge&logo=homeassistant&logoColor=white)](https://www.home-assistant.io)

</div>

---

## Installation

### HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=YasogaN&repository=ha-horizon-pv&category=integration)

1. Go to **HACS** → **Integrations**
2. Click the three dots → **Custom repositories**
3. Add `https://github.com/YasogaN/ha-horizon-pv` with category **Integration**
4. Click **Download** on Horizon Solar Forecast
5. Restart Home Assistant

### Manual

Copy `custom_components/horizon/` into your HA `custom_components/` directory and restart.

---

## Usage/Examples

### Quick Start

```yaml
# Recommended automation — train daily at 06:00
alias: Horizon Daily Learn
trigger:
  - platform: time
    at: "06:00:00"
action:
  - service: horizon.learn
```

```yaml
# Bootstrap from recorder history on first install
service: horizon.bootstrap
data:
  days: 14
```

### Sensors

| Sensor                             | State                | Attributes                                                                     |
| ---------------------------------- | -------------------- | ------------------------------------------------------------------------------ |
| `sensor.horizon_forecast_power`    | Current PV power (W) | `forecast` (96 15-min predictions), `generated_at`, `total_energy_kwh`         |
| `sensor.horizon_training_days`     | Training day count   | `last_training_date`, `prediction_mode`, `observed_peak_w`, `sgd_coefficients` |
| `sensor.horizon_model_diagnostics` | Prediction mode      | `training_days`, `last_training_date`, `physics_peak_w`                        |

### Services

| Service                   | Description                                      |
| ------------------------- | ------------------------------------------------ |
| `horizon.update_forecast` | Fetch weather and recalculate forecast           |
| `horizon.learn`           | Train model on yesterday's actual production     |
| `horizon.bootstrap`       | Scan recorder history for batch training         |
| `horizon.get_state`       | Return model state (training_days, mode, peak_w) |

---

## Configuration

All fields are configured via the Home Assistant UI (Settings → Devices & Services → Add Integration → Horizon Solar Forecast).

| Field                  | Type      | Default       | Description                                                   |
| ---------------------- | --------- | ------------- | ------------------------------------------------------------- |
| Name                   | str       | "Horizon"     | Integration instance name                                     |
| PV Power Sensor        | entity_id | **required**  | Sensor reporting current PV output in W                       |
| PV Daily Energy Sensor | entity_id | optional      | Sensor that resets at midnight (cumulative kWh)               |
| Latitude               | float     | from HA       | System latitude                                               |
| Longitude              | float     | from HA       | System longitude                                              |
| Timezone               | str       | from HA       | System timezone                                               |
| Panel Azimuth          | float     | 180°          | Direction panels face (0° = North)                            |
| Panel Tilt             | float     | 35°           | Panel tilt from horizontal                                    |
| Initial Peak Power     | float     | auto-detected | Observed peak PV in W                                         |
| Bootstrap Days         | int       | 7             | Days of history for initial training (0 = start from scratch) |
| Forecast Days          | int       | 2             | Days of forecast to fetch from Open-Meteo                     |

---

## How It Works

![Architecture Diagram](https://s6.imgcdn.dev/YHdqrh.png)

### Prediction Lifecycle

| Mode             | Condition         | Blend                 |
| ---------------- | ----------------- | --------------------- |
| Cold Start       | training_days < 3 | 100% physics formula  |
| Transition Phase | 3–13 days         | 50% SGD + 50% physics |
| Steady State     | 14+ days          | 80% SGD + 20% physics |

### Features (12)

| Feature                      | Source              | Unit    |
| ---------------------------- | ------------------- | ------- |
| `clear_sky_panel_irradiance` | Physics calculation | W/m²    |
| `cloud_cover`                | Open-Meteo          | %       |
| `solar_elevation_deg`        | Physics calculation | deg     |
| `hour_sin`, `hour_cos`       | Time encoding       | [-1, 1] |
| `shortwave_radiation`        | Open-Meteo          | W/m²    |
| `temperature_2m`             | Open-Meteo          | °C      |
| `relative_humidity_2m`       | Open-Meteo          | %       |
| `wind_speed_10m`             | Open-Meteo          | km/h    |
| `cloud_cover_low/mid/high`   | Open-Meteo          | %       |

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Summary of the MIT License

The **MIT License** is a permissive open-source license that allows users significant freedom with minimal conditions.

#### Key Permissions:
1. **Freedom to Use** — for any purpose, including commercial use
2. **Freedom to Modify** — modify the software as needed
3. **Freedom to Distribute** — distribute original or modified copies
4. **Freedom to Sell** — sublicense, distribute, and sell the software

#### Key Conditions:
- **Attribution** — original copyright notice and MIT license text must be included

#### No Warranty:
The software is provided "as is," with no warranties. The author is not liable for damages.

For full details, refer to the [LICENSE](LICENSE) file.

---

## Contributing

Contributions are welcome! Feel free to open issues or pull requests.

---

## Acknowledgements

This project is a complete rewrite of **PV Forecast Planner** by [wolpa29](https://github.com/wolpa29). The original project provided the Open-Meteo fetching routines, solar position calculations, and Home Assistant integration patterns that Horizon builds upon. Horizon replaces the offline-trained XGBoost approach with an online self-learning SGD model, adds automatic daily training via the HA recorder, and removes all external ML dependencies.

### Dependencies

- [Open-Meteo API](https://open-meteo.com) — free weather forecast data
- [Home Assistant Recorder](https://www.home-assistant.io/integrations/recorder/) — native statistics storage
