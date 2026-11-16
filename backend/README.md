# AgroPhasor Local Backend — ODE 1–5 Physics & API Engine

This module implements the five coupled agrophysical ODE engines (**ODE 1–5**), parcel simulation services, multi-objective crop rotation optimizer, and REST API routes of **AgroPhasor**, ready to ingest data from **NASA POWER** and **SRTM** APIs and simulate each 30×30 m cell.

---

## 🚀 Starting the Backend Locally

### Option 1: Run the unified Python server (Recommended)
From the project root, run:
```bash
python server.py
```
The web application and `/api/v1/` endpoints will be available at:
👉 `http://127.0.0.1:5173`

*(If FastAPI/Uvicorn is installed in your environment, you can also run `uvicorn backend.main:app --host 127.0.0.1 --port 5173 --reload` and inspect interactive docs at `http://127.0.0.1:5173/docs`).*

### Option 2: Use it directly as a Python module
```python
from backend.services.simulation_service import SimulationService

# nasa_data comes directly from the NASA POWER response
result = SimulationService.run_field_simulation(
    nasa_hourly_data=nasa_response["properties"]["parameter"],
    grid_cells=[
        {"cell_id": "0_0", "altitude_m": 3200.0, "slope_deg": 3.0, "aspect_deg": 180.0},
        {"cell_id": "0_1", "altitude_m": 3230.0, "slope_deg": 10.0, "aspect_deg": 90.0}
    ],
    crop_id="papa",       # 'papa', 'maiz', 'haba', 'barbecho'
    soil_water_mm=55.0    # Root-zone soil water level (mm)
)
```

---

## 📡 API Endpoints

### 1. `POST /simulate/edo1` (3D Parcel Simulation)
Receives the 30×30 m cell grid generated on the map and the raw hourly JSON from NASA POWER.

**Example Request (JSON):**
```json
{
  "crop_id": "papa",
  "soil_water_mm": 50.0,
  "ref_altitude_m": 3200.0,
  "nasa_hourly_data": {
    "T2M": { "2023010100": 5.9, "2023010112": 15.7 },
    "ALLSKY_SFC_SW_DWN": { "2023010100": 0.0, "2023010112": 2.7 },
    "RH2M": { "2023010100": 95.0, "2023010112": 46.0 }
  },
  "grid_cells": [
    {
      "cell_id": "0_0",
      "altitude_m": 3200.0,
      "slope_deg": 2.0,
      "aspect_deg": 180.0
    },
    {
      "cell_id": "0_1",
      "altitude_m": 3245.0,
      "slope_deg": 8.5,
      "aspect_deg": 90.0
    }
  ]
}
```

**Example Response (JSON):**
```json
{
  "crop": "Potato",
  "soil_water_mm": 50.0,
  "lot_mean_temp": 14.82,
  "cells_count": 2,
  "cells": [
    {
      "cell_id": "0_0",
      "altitude_m": 3200.0,
      "mean_canopy_temp": 15.1,
      "max_canopy_temp": 24.5,
      "min_canopy_temp": 4.8,
      "lissajous_area": 48.2,
      "thermal_shield": "Cobalt Blue (Optimal)",
      "fever_hours_count": 0,
      "hourly_canopy_temps": [5.0, "...", 24.5, "...", 5.2]
    }
  ]
}
```

### 2. `GET /crops`
Lists the available crops and their thermal comfort and wilting-point parameters.

### 3. Additional Implemented Endpoints (ODE 1–5, Calibration & Rotation Optimization)
- **Health, Catalog & Geolocation:** `GET /health`, `GET /api/v1/health`, `GET /api/places`, `GET /api/v1/crop-cycles`, `GET /api/v1/crop-catalog`
- **Parcel Simulation, Forecasting & Rotation Endpoints:** `POST /api/v1/parcelas/simulacion` (alias `/api/v1/parcelas/edo1`), `POST /api/v1/parcelas/rotaciones`, `POST /api/v1/rotaciones`, `POST /api/v1/simular`, `POST /api/v1/parcelas`, `POST /api/v1/clima/predecir` (alias `/api/v1/climate/forecast`), `POST /simulate/edo1/point`
- **Real-Time Satellite Calibration:** `POST /calibrate/satellite` (alias `/api/v1/calibrar-satelital`)
- **ODE 2–5 Solvers:** `POST /simulate/edo2` (`/api/v1/simular/edo2` in the built-in HTTP fallback), `POST /simulate/edo3` (`/api/v1/simular/edo3`), `POST /simulate/edo3/rotation` (`/api/v1/simular/edo3/rotacion`), `POST /simulate/edo4` (`/api/v1/simular/edo4`), `POST /simulate/edo4/grid` (`/api/v1/simular/edo4/malla`), `POST /simulate/edo5` (`/api/v1/simular/edo5`), `POST /simulate/edo5/step` (`/api/v1/simular/edo5/paso`), `POST /simulate/edo5/grid` (`/api/v1/simular/edo5/malla`)
- **Catalog Validators:** `POST /api/v1/validate/catalog`, `POST /api/v1/validate/catalog/edo3`..`edo5`

---

## 🧪 Running Unit Tests
To verify that the physics, satellite calibration, rotation graph search, and API endpoints pass all checks:
```bash
python -m pytest tests
```
