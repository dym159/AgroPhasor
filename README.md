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
- **ODE 1 — Canopy Thermal Energy Balance (`edo1_engine.py`, `topoclimatic.py`):**
  - Solves hourly canopy temperature $T(t)$ per 30×30 m cell using an exact integrating-factor step with Penman linearization, topoclimatic altitude lapse rates, slope/aspect solar irradiance adjustments from SRTM v3, and transpiration cooling modulated by root-zone water availability.
  - Computes 24-hour air-vs-canopy **Lissajous phase-portrait trajectories**, thermal shield states, and frost/heat stress alerts.
- **ODE 2 — Root-Zone Water Balance (`edo2_engine.py`, `edo2_validator.py`):**
  - Tracks daily root-zone soil moisture $W(t)$ bounded in $[0, W_{cc}(H)]$ via $\frac{dW}{dt} = P_0(t)\cos\theta + \eta_{\text{irrig}} I(t) - ET_c(T, W) - k_d \sin\theta \, W$, converting excess moisture above $W_{cc}(H)$ directly into surface runoff.
  - Models relative stomatal conductance $\gamma_c(W)/\gamma_{\max}$, biomass-shaded soil evaporation ($E_{\text{suelo},0}(W/W_{cc})e^{-\lambda_B B}$), hillslope gravitational drainage, predictive fast-drying warnings, wilting alerts ($W \le W_{\text{pmp}}$), and replenishment irrigation suggestions $(W_{cc} - W)/\eta_{\text{irrigation}}$.
- **ODE 3 — Soil NPK Chemical Vector Dynamics (`edo3_engine.py`, `edo3_validator.py`):**
  - Integrates available Nitrogen, Phosphorus, and Potassium $\mathbf{N}_{i,j}(t) = [N, P, K]^T$ via the decoupled exact analytical solution $\exp(-\Lambda \Delta t)\mathbf{N} + \Delta t\,\phi_1(\Lambda \Delta t)\mathbf{S}$, guaranteeing unconditional non-negativity.
  - Models legume biological nitrogen fixation ($F_{\text{fix}}$), root phosphorus solubilization ($F_{\text{sol}}$) and erosion-driven particulate P loss, stover potassium recycling during fallow transitions, CEC-modulated vertical N/K leaching, soil pH/EC availability ($\phi_{\text{pH,EC}}$), $Q_{10}$ microbial kinetics, and **Liebig's Law of the Minimum** ($\eta_{\text{nutrientes}}$).
- **ODE 4 — Logistic Biomass Growth & Harvest Economics (`edo4_engine.py`, `edo4_validator.py`, `edo4_data_adapter.py`):**
  - Couples daily above-ground biomass $B(t) \in [0, B_{\max}]$ to incident radiation $f_{\text{rad}}$, the photosynthetic thermal envelope $\eta_T(T)$, water limitation $f_W(W)$, Liebig nutrient efficiency $\eta_N$, and $Q_{10}$ maintenance respiration.
  - Executes discrete harvest and planting jumps—computing commercial yield $Y_k = HI \cdot (1 - r_{\text{res}}) \cdot B(t^-)$, residual stover $B(t^+) = r_{\text{res}} B(t^-)$, organic matter incorporation $\Delta OM = \xi_{OM} B(t^-)$, and bare-soil transition decay $\frac{dB}{dt} = -k_{\text{dec}} B$—and estimates canopy cover and a simulated NDVI proxy.
- **ODE 5 — Topsoil Erosion & Fertile Depth Evolution (`edo5_engine.py`, `edo5_validator.py`):**
  - Tracks fertile soil thickness $H(t)$ (mm) via $\frac{dH}{dt} = -k_{\text{er}}(q)\, P_0(t)\,\sin\theta\, e^{-\lambda_B B(t)}$, combining rainfall $P_0(t)$, SRTM slope $\sin\theta$, discrete crop/tillage erodibility $k_{\text{er}}(q)$, and exponential canopy/stover cover protection.
  - Dynamically contracts root-zone water thresholds ($W_{cc}(H) = \theta_{fc} H$, $W_{\text{pmp}}(H) = \theta_{wp} H$), tracks nutrient runoff drag and 3D mesh subsidence, shifts soil RGB color from fertile brown toward bedrock gray, and raises bedrock exposure alerts when $H \le 0.05\text{ mm}$.

### 2. Multi-Objective Rotation Optimizer, Climate Forecasting & Coupled Services (`backend/services/`, `backend/core/climate_generator.py`, `rotation_ranking.py`)
- **Coupled Daily Simulation & Monte Carlo Climate Forecasting (`coupled_model.py`, `plan_service.py`, `climate_service.py`, `climate_generator.py`):** Advances all five ODEs across multi-stage planting/harvest timelines with 14-day fallow transitions, soil water/NPK/stover/depth carryover, and stochastic future trajectories calibrated from 3-year historical NASA POWER records (`Fourier OLS K=2 + AR(1) residuals + seasonal Bernoulli-Gamma rainfall`, plus `delta_T_whatif` / `delta_P_pct_whatif` stress shifts).
- **Pareto Front & Priority Knobs (`rotation_service.py`, `rotation_ranking.py`, `frontend/src/utils/rotationRanking.js`):**
  - Evaluates multi-campaign crop sequences (`papa` Native Potato, `maiz` Amylaceous Maize, `frijol` Dry Bean) across historical or Fourier/AR(1)-Gamma Monte Carlo climate trajectories, dry-year stress scenarios (`DRY_RAIN_FACTOR = 0.7`), and configurable multi-scenario climate uncertainty ensembles (`uncertainty_samples=20` by default).
  - Filters non-dominated Pareto routes across four objectives controlled by interactive priority knobs (`w1` Water Austerity, `w2` Best Final Soil, `w3` Highest Profit, `w4` Fastest Rotation) and re-ranks cached candidates on the client in `< 1 ms` as sliders move.

### 3. Interactive Web Application (`frontend/`)
- **Satellite Parcel Selector (`parcelSelectorMap.js`):** Leaflet + Geoman polygon drawing/editing over Esri World Imagery (with canvas overzoom up to zoom 21) and optional NASA GIBS HLS Sentinel-2 reflectance layer, Nominatim locality search, geolocation, and per-cell thermal overlay tooltips.
- **2.5D/3D Terrain & Thermal Shield Visualizer (`terrainVisualizer.js`, `parcelSimulationMesh.js`):** Interactive 3D extruded parcel mesh showing SRTM relief, cumulative erosion sinking, soil fertility color, elevated 24-hour Lissajous thermal shield loops with an hour slider (`00:00–23:00`), and a bare-soil transition toggle.
- **Decision & Planning Panels:** Strategy mode presets (`strategyPanel.js`), auto-balancing priority knobs with lock/unlock (`knobsPanel.js`), filterable draggable crop catalog (`cropsPanel.js`), multi-phase planting calendar with date inspection (`timelineBar.js`), and recommended rotation comparison with one-click timeline application (`rotationsPanel.js`).

### 4. Verification & Test Coverage (`tests/`)
- **65 Python unit and integration tests** (`py -m unittest discover -s tests -v`) validating ODE 1–5 physics, catalog schemas, NASA/SRTM adapters, Fourier/AR(1)-Gamma climate forecasting, multi-period state carryover, and Pareto rotation ranking.
- **8 Node.js tests** (`node --test tests/test_terrain.mjs tests/test_rotation_ranking.mjs`) validating Terrarium DEM decoding, 3D mesh erosion geometry, and client-side Pareto re-ranking across knobs `w1`–`w4`.

---

## 🚀 Quick Start (Local Development)

From the repository root, install dependencies and start the unified Python server (which serves both the frontend and `/api/v1/` endpoints on port `5173`):

```bash
python -m pip install -r requirements.txt
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
# Python backend & physics test suite (65 tests)
python -m unittest discover -s tests -v

# Node.js frontend unit tests (8 tests)
node --test tests/test_terrain.mjs tests/test_rotation_ranking.mjs
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
- [AgroPhasor Mathematical & Physical Specification (PDF)](Agrophasor.pdf)
