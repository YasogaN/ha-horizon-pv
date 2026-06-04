# PV Forecast Tools

Optional local tools for creating a trained PV forecast model. Home Assistant does not load this folder.

## Setup

```bash
cd tools
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill in `LATITUDE` and `LONGITUDE` in `.env`. For SunnyPortal scraping, also fill in `SUNNYPORTAL_EMAIL` and `SUNNYPORTAL_PASSWORD`.

If you do not use SunnyPortal, only fill in the location/PV values and create this file yourself:

```text
tools/data/pv_measurements/pv_measurements.csv
```

Required layout:

```csv
timestamp,pv_power_w
2026-06-01 10:00:00,4321.0
2026-06-01 10:15:00,4780.0
```

## Scripts

- `update_data.py`: downloads SunnyPortal data, fetches historical Open-Meteo data, and rebuilds the dataset.
- `train.py`: builds the dataset if needed and trains the XGBoost model.
- `pv_measurements.py`: converts SunnyPortal raw CSV files to the generic `pv_measurements.csv`.
- `scrapers/sunnyportal.py`: downloads SunnyPortal Energy Balance CSV files.
- `scrapers/weather.py`: fetches historical Open-Meteo forecast and observed weather CSV files.
- `ml/build_dataset.py`: creates the ML training dataset.
- `ml/train_model.py`: trains the model and writes model artifacts.
- `config/settings.py`: reads `.env` and defines local paths/settings.

## Commands

```bash
venv/bin/python update_data.py
venv/bin/python train.py
```

Useful `update_data.py` flags:

- `--skip-pv`: do not download SunnyPortal raw files, but still rebuild `pv_measurements.csv`.
- `--skip-measurements`: keep your existing `pv_measurements.csv`.
- `--skip-weather`: keep existing Open-Meteo CSV files.
- `--skip-dataset`: keep the existing ML dataset.

Without SunnyPortal, place your own `pv_measurements.csv` first and run:

```bash
venv/bin/python update_data.py --skip-pv --skip-measurements
venv/bin/python train.py
```

Data folders:

- `data/sunnyportal_raw/`: SunnyPortal-only raw CSV files.
- `data/pv_measurements/`: generic PV measurements CSV.
- `data/ml/`: generated training dataset and weather feature files.

The trained Home Assistant model files are written to:

```text
tools/models/pv_forecast_xgboost/model.json
tools/models/pv_forecast_xgboost/features.json
```

Copy those two files to your Home Assistant model directory, for example:

```text
/config/pv_forecast_planner/models/default/
```

Generated data stays in `tools/data/` and is ignored by git.
