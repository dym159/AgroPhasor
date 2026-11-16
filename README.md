# 🚀 AgroPhasor (Nasa_AgroFarm)

> **NASA Space Apps Challenge 2026**  
> **Challenge:** *Field Shift: Adapting Farms with NASA Data*  
> **Solution:** Mechanistic Agro-Physical Digital Twin and Spatiotemporal Multi-Objective Crop Rotation Optimizer under Climate Stress.

---

## 📋 Project Overview

**AgroPhasor** is a farmer-oriented web platform that models an agricultural parcel as a coupled thermodynamic, hydrological, chemical, biological, and geomorphological dynamical system. Using **NASA POWER** agroclimatological time series, **SRTM v3** 30×30 m digital elevation models, **NASA GIBS (HLS Sentinel-2)** satellite layers, Fourier/AR(1)-Gamma Monte Carlo climate forecasting, and regional **MIDAGRI** farm-gate prices, AgroPhasor simulates parcel evolution at the cell level and recommends Pareto-optimal multi-season crop rotations.

---

## 📍 Current Project Status (What Is Implemented)

The repository currently integrates the full end-to-end stack—from the five coupled differential equation engines in Python to the interactive 2.5D/3D web workspace:

### 1. Five Coupled Agro-Physical ODE Engines (`backend/core/` & `backend/models/`)
- **ODE 1 — Canopy Thermal Energy Balance (`edo1_engine.py`, `topoclimatic.py`, `physics.py`, `shield_calibration.py`):**
  - Solves hourly canopy temperature $T(t)$ per 30×30 m cell using an exact integrating-factor step with frozen daily latent heat flux ($\bar{Q}_{\text{lat}}$ held constant across fast thermal sub-steps, `h_eff = crop.hc`), zero stomatal conductance at night and below wilting point ($W \le W_{\text{pmp}}$), topoclimatic altitude lapse rates, SRTM v3 slope/aspect solar adjustments, and transpiration cooling modulated by root-zone water availability.
  - Computes 24-hour air-vs-canopy **Lissajous phase-portrait trajectories** ($A_L$), biome-calibrated Hill-curve Environmental Shield scores & continuous Red-to-Blue RGB gradients (`compute_shield_state_and_color`, validated via 4-fold stratified CV in `shield_calibration.py`), and frost/heat stress alerts.
- **ODE 2 — Root-Zone Water Balance (`edo2_engine.py`, `edo2_validator.py`):**
  - Tracks daily root-zone soil moisture $W(t)$ bounded in $[0, W_{cc}(H)]$ via $\frac{dW}{dt} = P_0(t)\cos\theta + \eta_{\text{irrig}} I(t) - ET_c(T, W) - k_d \sin\theta \, W$, converting excess moisture above $W_{cc}(H)$ directly into surface runoff.
  - Models relative stomatal conductance $\gamma_c(W)/\gamma_{\max}$, biomass-shaded soil evaporation ($E_{\text{soil},0}(W/W_{cc})e^{-\lambda_B B}$), hillslope gravitational drainage, predictive fast-drying warnings, wilting alerts ($W \le W_{\text{pmp}}$), and replenishment irrigation suggestions $(W_{cc} - W)/\eta_{\text{irrigation}}$.
- **ODE 3 — Soil NPK Chemical Vector Dynamics (`edo3_engine.py`, `edo3_validator.py`):**
  - Integrates available Nitrogen, Phosphorus, and Potassium $\mathbf{N}_{i,j}(t) = [N, P, K]^T$ via the decoupled exact analytical solution $\exp(-\Lambda \Delta t)\mathbf{N} + \Delta t\,\phi_1(\Lambda \Delta t)\mathbf{S}$, guaranteeing unconditional non-negativity.
  - Models legume biological nitrogen fixation ($F_{\text{fix}}$), root phosphorus solubilization ($F_{\text{sol}}$), exact $\phi_2$-integrated particulate erosion loss (`erosion_npk_kg_ha`), stover potassium recycling during fallow transitions, CEC-modulated vertical N/K leaching, soil pH/EC availability ($\phi_{\text{pH,EC}}$), $Q_{10}$ microbial kinetics, and **Liebig's Law of the Minimum** ($\eta_{\text{nutrients}}$).
- **ODE 4 — Logistic Biomass Growth & Harvest Economics (`edo4_engine.py`, `edo4_validator.py`, `edo4_data_adapter.py`):**
  - Couples daily above-ground biomass $B(t) \in [0, B_{\max}]$ to incident radiation $f_{\text{rad}}$, the photosynthetic thermal envelope $\eta_T(T)$, water limitation $f_W(W)$, Liebig nutrient efficiency $\eta_N$, and $Q_{10}$ maintenance respiration.
  - Executes both full harvest jumps—computing commercial yield $Y_k = HI \cdot (1 - r_{\text{res}}) \cdot B(t^-)$, residual stover $B(t^+) = r_{\text{res}} B(t^-)$, organic matter incorporation $\Delta OM = \xi_{OM} B(t^-)$—and partial multi-harvest cuts (`execute_partial_cut`, e.g., perennial strawberry), bare-soil transition decay $\frac{dB}{dt} = -k_{\text{dec}} B$, canopy cover, and simulated NDVI proxies.
- **ODE 5 — Topsoil Erosion & Fertile Depth Evolution (`edo5_engine.py`, `edo5_validator.py`):**
  - Tracks fertile soil thickness $H(t)$ (mm) via $\frac{dH}{dt} = -k_{\text{er}}(q)\, P_0(t)\,\sin\theta\, e^{-\lambda_B B(t)}$, combining rainfall $P_0(t)$, SRTM slope $\sin\theta$, discrete crop/tillage erodibility $k_{\text{er}}(q)$, and exponential canopy/stover cover protection.
  - Dynamically contracts root-zone water thresholds ($W_{cc}(H) = \theta_{fc} H$, $W_{\text{pmp}}(H) = \theta_{wp} H$), tracks nutrient runoff drag, rainfall-driven height variation (`compute_terrain_height_variation`), 3D mesh subsidence, soil vitality & chromatic shift from fertile brown `(101, 67, 33)` toward bedrock gray `(128, 128, 128)`, and bedrock exposure alerts when $H \le 0.05\text{ mm}$.

### 2. Satellite Calibration, Exact Rotation Optimizer & Climate Forecasting (`backend/core/`, `backend/rotation/`, `backend/services/`)
- **Real-Time Satellite Calibration Engine (`satellite_calibration.py`):**
  - Tunes thermal parameters (`h_c`, `Cp`, `h_suelo`) against ECOSTRESS LST / NASA POWER `TS` via bounded Levenberg-Marquardt (`calibrate_edo1_thermal`), hydrological drydown rates (`kd`, `E_suelo0`) following GPM/IMERG events against SMAP / OpenET (`calibrate_edo2_hydrology`), and radiation-use scaling (`kp_c`) against Sentinel-2 / Landsat NDVI/EVI time series (`calibrate_edo4_biomass`), exposed via `POST /calibrate/satellite`.
- **Exact Constrained Rotation Graph Optimizer (`backend/rotation/` & `backend/data/peru_departments.geojson`):**
  - Searches multi-campaign rotations (2–6 stages) over the multiscale coupled daily simulator (`coupled_model.py`, `avanzar_un_dia_celda`), enforcing botanical-family alternation, regional INIA planting calendars detected automatically from Peruvian department boundaries (`peru_departments.geojson`, geoBoundaries ADM1 `90a1d52`), and scenario survival thresholds (`mean` / `worst`).
  - Uses `gemini-code.json` + `backend/data/crop_catalog.json` (core species `papa`, `maiz`, `frijol`, `fresa`, `barbecho` plus 20+ documented Peruvian reference cultivars) and MIDAGRI farm-gate prices to construct the Pareto front across four objectives (`w1` Water Austerity, `w2` Soil Conservation, `w3` Net Profit, `w4` Cycle Speed) with instant client-side re-ranking (`< 1 ms`).
- **Monte Carlo Climate Forecasting (`climate_generator.py`, `climate_service.py`):**
  - Calibrates truncated Fourier OLS (`K=2`) + AR(1) residual + seasonal Bernoulli-Gamma precipitation generators from historical NASA POWER series, supporting `delta_T_whatif` and `delta_P_pct_whatif` scenario stress testing.

### 3. Interactive Web Application (`frontend/`)
- **Satellite Parcel Selector (`parcelSelectorMap.js`):** Leaflet + Geoman polygon drawing/editing over Esri World Imagery (with canvas overzoom up to zoom 21) and optional NASA GIBS HLS Sentinel-2 reflectance layer, Nominatim locality search, geolocation, and per-cell thermal overlay tooltips.
- **2.5D/3D Terrain & Thermal Shield Visualizer (`terrainVisualizer.js`, `parcelSimulationMesh.js`):** Interactive 3D extruded parcel mesh showing SRTM relief, cumulative erosion sinking, soil fertility color, elevated 24-hour Lissajous thermal shield loops with an hour slider (`00:00–23:00`), and a bare-soil transition toggle.
- **Decision & Planning Panels:** Strategy mode presets (`strategyPanel.js`), auto-balancing priority knobs with lock/unlock (`knobsPanel.js`), filterable draggable crop catalog loaded dynamically via `/api/v1/crop-catalog` (`cropsPanel.js`), multi-phase planting calendar with date inspection (`timelineBar.js`), and the regional rotation workflow panel supporting 3–6 stages, Peruvian department detection/override, and one-click Apply/Undo timeline synchronization (`rotationsPanel.js`).

### 4. Verification & Test Coverage (`tests/`)
- **109 Python unit, regression, and agronomic validation tests** (`pytest tests`) validating ODE 1–5 numerical stability and PDF equations, satellite out-of-sample backtesting, 4-fold biome shield calibration, partial harvests, Fourier/AR(1)-Gamma climate forecasting, regional department matching, exact/adaptive rotation graph search, and FastAPI/HTTP API contracts.
- **15 Node.js tests** (`npm test` / `node --test tests/*.mjs`) validating Terrarium DEM decoding, 3D mesh erosion/rain subsidence geometry, soil color vitality, client-side Pareto re-ranking across knobs `w1`–`w4`, and rotation UI workflows.

---

## 🚀 Quick Start (Local Development)

From the repository root, install runtime/dev dependencies and start the unified Python server (which serves both the frontend and `/api/v1/` endpoints on port `5173`):

```bash
python -m pip install -r requirements-dev.txt
python server.py
```

Then open [http://127.0.0.1:5173](http://127.0.0.1:5173) in your browser.

> **Note:** On Windows with the Python launcher installed, you can use `py -m pip install -r requirements.txt` and `py server.py`. To serve a pre-built frontend directory, set `AGROPHASOR_FRONTEND_DIR` to the folder containing `index.html` before starting `server.py`.

---

## 🧭 Using the Application

1. **Draw Your Parcel:** Pan or search for any locality (via Nominatim), draw your parcel polygon on the satellite map, and inspect the 30×30 m cells colored by mean canopy temperature. Each cell uses SRTM v3 elevation, slope, and aspect combined with hourly NASA POWER forcing. With Shapely and PyProj installed, cells are clipped to the exact parcel boundary.
2. **Inspect the 3D Terrain & Shield:** Click **Confirm parcel** (or **3D View**) to open the interactive 3D terrain. Drag to rotate (`Shift + drag` to pan), use the **Shield hour** slider to step through the 24 simulated hours, and toggle **Bare soil** to inspect the fallow transition regime and rainfall exposure alert.
3. **Adjust Strategies & Priority Knobs:** Select a strategy preset (**Maximum Yield**, **Optimal Balance**, **Maximum Resilience**) or drag the priority knobs (`w1`–`w4`). The **Recommended rotation** panel immediately re-ranks the Pareto-optimal crop sequences to match your weights.
4. **Build or Apply a Planting Timeline:** Click **Apply to timeline** on a recommended rotation—or add phases manually with **+ Phase** and drag crops from the catalog—and use **Simulate date** to inspect parcel evolution at any date along the rotation.

### Simulation & Data Notes
- The parcel simulator searches for the most recent historical day within the last 365 days that has 24 valid hourly records of temperature, solar radiation, and relative humidity from NASA POWER.
- Initial root-zone water is estimated from daily `GWETROOT` (or 70% of field capacity $W_{cc}$ when unavailable). Water, nutrients, biomass, and fertile topsoil depth advance on a daily step, and end-of-day water/chemical states feed the hourly shield index.
- Each parcel request is capped at 500 cells (30×30 m). Place search queries Nominatim only on form submission and uses an in-memory cache and rate limiter (`AGROPHASOR_GEOCODER` can be set for custom geocoding endpoints; see the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)).

---

## 🧪 Running Tests

```bash
# Python backend, physics, satellite/shield calibration & rotation test suite (109 tests)
python -m pytest tests

# Node.js frontend unit & UI workflow tests (15 tests)
npm test
```

---

## 🛡️ Security & Git Hooks (Linear Task CC-01)

To prevent leaking private keys, cloud credentials, `.env` files, or secrets into Git history, the repository includes versioned **Git Hooks** and local CI checks powered by **Gitleaks**.

### 1. Prerequisites

Install **Gitleaks** locally (if unavailable, the scripts automatically fall back to Docker):

```bash
# Windows (PowerShell with winget)
winget install Gitleaks.Gitleaks

# macOS / Linux (Homebrew)
brew install gitleaks
```

### 2. Enable Git Hooks in Your Local Clone

Run once from the repository root:

```bash
git config core.hooksPath .githooks
```

### 3. Configured Hooks
- **`pre-commit` (`.githooks/pre-commit`):**
  - Blocks sensitive staged files (`.env`, `*.pem`, `*.key`, `id_rsa`, `*gcp*.json`, `.netrc`).
  - Runs `gitleaks protect --staged -v --redact` on staged changes.
  - Detects unresolved merge conflict markers (`<<<<<<< / ======= / >>>>>>>`).
  - Warns when committing directly to `main`.
- **`pre-push` (`.githooks/pre-push`):**
  - Runs `./check-ci.sh` before pushing to remote; aborts the push if any secret scan or validation fails.

### 4. Local CI Validator (`check-ci.sh` / `check-ci.ps1`)

Run the full verification suite at any time before opening a Pull Request:

```bash
./check-ci.sh
# Or on Windows PowerShell:
./check-ci.ps1
```

### 5. Local Environment Configuration

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Configure the required parameters in `.env`. **Never commit `.env` to Git.**

---

## 📚 Technical Documentation

- [AgroPhasor Master Plan](docs/PLAN_MAESTRO_AGROPHASOR.md)
- [Backend Physics & API Guide](backend/README.md)
- [Local Environment Setup Guide](ENTORNO_LOCAL.md)
- [ODE Numerical Corrections & Verification](docs/CORRECCIONES_EDO.md)
- [Exact Rotation Graph Optimizer](backend/rotation/README.md)
- [Rotation Panel UI Behavior](frontend/ROTACIONES.md)
- [Peru Crop Rotation Data Sources](docs/fuentes-rotacion-peru.md)
- [60-Crop Peru Rotation Inventory](docs/inventario-60-cultivos-peru.md)
- [AgroPhasor Mathematical & Physical Specification (PDF)](Agrophasor.pdf)
