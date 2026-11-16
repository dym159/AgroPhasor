# Exact Rotations

`POST /api/v1/parcelas/rotaciones` preserves `/api/v1/rotaciones` unchanged.
The implicit graph uses exact DFS, forbids consecutive crops from the same botanical family, and chains catalog cycle durations plus fallow transitions. Indices in `fixed` are zero-based.

Minimal input (illustrative contract values, not field measurements):

```json
{
  "m": 3, "start_date": "2026-11-15", "crop_ids": ["papa", "maiz", "frijol"],
  "latitude": -12.06, "longitude": -75.21,
  "initial_state": {"W": 100, "N": 100, "P": 40, "K": 120,
                    "H": 400, "residue": 0, "OM": 3},
  "transition_days": 14, "residue_fraction": 0.5, "slope_deg": 0,
  "irrigation_mm_day": 0, "irrigation_cost_usd_mm_ha": 0,
  "fixed": {"0": "papa"}, "route": "B_balance"
}
```

`W` and `H` are in mm; `NPK` in kg/ha; stover residue in t/ha; `OM` in percent.
Prices `prices_usd_t` (USD/t) and costs `costs_usd_ha` (USD/ha) must be provided explicitly to avoid treating fallback economic defaults as observed data. When missing, `f3` is globally `None`, route `C2` is disabled, and active weights are renormalized. `weights`: four numbers summing to one.

`backend/data/crop_catalog.json` supports `grupo`, `calendarios`, and `economia` inside each crop record. `calendarios` is keyed by region, with each calendar containing `duracion_dias`, `meses_siembra`, and `fuente`. `economia` is nested by region and campaign, with each record containing `precio_usd_t`, `costo_usd_ha`, and `fuente`. Region keys are matched ignoring accents, casing, and redundant whitespace.

When `region` is supplied, the recommender uses the regional duration and planting window if present. When both `region` and `campaign` are supplied, it also uses the economic profile for that campaign. Explicit request windows, prices, and costs override catalog records. The selector fetches active crops from `GET /api/v1/crop-catalog`.

The `cultivos_referencia` section extends the recommender with documented cycle sheets. The engine uses baseline biophysical defaults for coefficients omitted from those reference sheets. Cycles published as ranges use a representative duration. Regional planting windows apply when the API receives a matching region.

The reference profile identifies the department from the parcel polygon. Boundaries in `backend/data/peru_departments.geojson` come from [geoBoundaries gbOpen, Peru ADM1](https://www.geoboundaries.org/api/current/gbOpen/PER/ADM1/) (version `90a1d52`, original public-domain source). Names and geometries were preserved with coordinates rounded to five decimal places.

The dashboard uses `adaptive` mode: small searches run exhaustively, while larger searches keep up to eight prefixes per stage chosen under distinct priorities, which may omit alternatives that an exhaustive search would find.

The UI sends `profile: "reference"` to compute without form inputs. That profile supplies baseline soil and management defaults and enables catalog fallback prices and costs. Explicit inputs and regional campaign economics take precedence when supplied.

The backend adapts nested sheets from `gemini-code.json` for crops absent from the flat catalog, giving priority to existing sheets. Rotations model each partial harvest cut prior to final harvest by removing the specified fraction from live biomass and counting it as estimated commercial yield; stages with cuts return `partial_harvest_dates`. Prices and costs from `gemini-code.json` serve as baseline references, while rotation margins use regional campaign data or explicit request inputs.

Optional fields: GeoJSON Polygon/MultiPolygon `geometry` (climate evaluated at centroid), per-crop `windows` (months 1..12), `drought_days` (infeasibility threshold), `survival_threshold` in `(0, 1]`, `aggregation`: `mean` / `worst`.
`periods`: list of `{"start": "YYYY-MM-DD"}` of length `m`; when supplied, only branches whose chained dates match exactly are admitted (no silent waiting is inserted and physical catalog durations are not altered).
`scenarios`: list of `{id, daily: {"MM-DD": [rain_mm, T_C, RH_pct, radiation_MJ_m2]}}`. Without explicit scenarios, the NASA climate loader is used. No synthetic perturbations or live network calls are performed during tests. Provided scenarios must cover all chained dates; any missing record raises a clear error.

Actual coupling: `PeriodSimulator` calls existing `advance_day`, `execute_harvest_event`, and `incorporate_residue`. It preserves `W`/`NPK`/`H`, thermal history, stover, and `OM`; planting incorporates stover and resets biomass to catalog `B0`. Internal constants and assumptions match the core engine. `g1` integrates $1 - \psi$ per day including transition; `g3` is cost minus revenue; `g4` counts days; `g2` records per-stage soil diagnostics; **`f2` is recomputed from final state** with `compute_soil_pareto_metric_f2` rather than summing repeated deficits. Objectives: $f_1 = \sum g_1 / \sum g_4$, $f_3 = 365 \sum g_3 / \sum g_4$, $f_4 = \sum g_4 / m$. Mean/worst-case objectives are computed over surviving scenarios and survival frequency is reported against total tested scenarios.

Changing route or priority knobs reuses the per-process LRU physics cache (16 entries). Pure route selection also works directly over the returned Pareto front. No synthetic defaults are used in production (tests only). The existing catalog and NASA data are unmodified. The endpoint models a single column with supplied slope rather than aggregating a spatially heterogeneous grid.

Tests: `python -m pytest tests/test_rotation_graph.py` and `bash ./check-ci.sh`.
Pending: `NAMOA*` (`astar` rejects execution explicitly; requires admissible stage lower bounds even with revenues and state-equivalence pruning, as cost dominance alone is insufficient).
Integration items pending: public Fourier/Monte Carlo scenario provider integration, spatial reference grid, and performance budget (outside this contract).
