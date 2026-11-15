# Backend Local de AgroPhasor — Motor de Física EDO 1

Este módulo implementa el motor de balance de energía térmica y temperatura del dosel (**EDO 1**) de **AgroPhasor**, listo para recibir datos de las APIs de **NASA POWER** y **SRTM**, y devolver la temperatura del dosel y el Escudo Térmico para cada celda de 30x30m.

---

## 🚀 Cómo Iniciar el Backend Localmente

### Opción 1: Levantar el servidor FastAPI
Desde la raíz del proyecto, ejecuta:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 5173 --reload
```
La documentación interactiva Swagger estará disponible de inmediato en:  
👉 `http://127.0.0.1:5173/docs`

### Opción 2: Usarlo directamente como módulo en Python
```python
from backend.services.simulation_service import SimulationService

# nasa_data viene directo de la llamada a NASA POWER
resultado = SimulationService.run_field_simulation(
    nasa_hourly_data=nasa_response["properties"]["parameter"],
    grid_cells=[
        {"cell_id": "0_0", "altitude_m": 3200.0, "slope_deg": 3.0, "aspect_deg": 180.0},
        {"cell_id": "0_1", "altitude_m": 3230.0, "slope_deg": 10.0, "aspect_deg": 90.0}
    ],
    crop_id="papa",       # 'papa', 'maiz', 'haba', 'barbecho'
    soil_water_mm=55.0    # Nivel hídrico de suelo
)
```

---

## 📡 Endpoints de la API

### 1. `POST /simulate/edo1` (Simulación de Parcela 3D)
Recibe la cuadrícula de celdas de 30x30m generadas en el mapa y el JSON crudo de NASA POWER.

**Ejemplo de Request (JSON):**
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

**Ejemplo de Response (JSON):**
```json
{
  "crop": "Papa",
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
      "thermal_shield": "Azul Cobalto (Óptimo)",
      "fever_hours_count": 0,
      "hourly_canopy_temps": [5.0, ..., 24.5, ..., 5.2]
    }
  ]
}
```

### 2. `GET /crops`
Lista los cultivos disponibles y sus parámetros de confort térmico y límites de marchitez.

---

## 🧪 Ejecución de Tests Unitarios
Para comprobar que la física y las fórmulas cumplen los 4 criterios de validación:
```bash
pytest -v tests/test_edo1_engine.py
```
