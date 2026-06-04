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

Fill in `SUNNYPORTAL_EMAIL`, `SUNNYPORTAL_PASSWORD`, `LATITUDE`, and `LONGITUDE` in `.env`.

## Scripts

- `update_data.py`: downloads SunnyPortal data, fetches historical Open-Meteo data, and rebuilds the dataset.
- `train.py`: builds the dataset if needed and trains the XGBoost model.
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
