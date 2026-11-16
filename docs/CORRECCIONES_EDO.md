# ODE Fixes Following the 2026-11-15 Audit

The mathematical reference is the 53-page technical specification PDF provided with the project.
These changes resolve the reproduced analytical findings; they do not constitute field
calibration with empirical measurements or general certification of agronomic accuracy.

## Equations and Diagnostics

- **ODE 1** applies the analytical solution with frozen latent heat flux $Q_{\text{lat}}$ at step start (Sec. 4.2). Penman slope substitution in dissipation was removed. Stomatal conductance is strictly zero below wilting point and at night; the daytime ramp matches the hydrological balance.
- **ODE 2** retains the exponential integral and the linear limit when $\lambda = 0$. If $W$ is exhausted in that limit, transpiration time is bounded to the true depletion time. Fluxes and $W$ maintain floating-point precision.
- **ODE 3** uses `expm1` for $\phi_1$ and evaluates diagnostics from the exact state integral $X' = S - \lambda X$. The spurious `0.10` factor affecting reported leaching was removed. Outputs `sources_npk_kg_ha`, `uptake_npk_kg_ha`, and `erosion_npk_kg_ha` allow full mass-balance checks for every nutrient alongside leaching.
- **ODE 4** applies the passed `k_dec` directly without multiplying by $Q_{10}$ during transition, allows $k_m = 0$, and preserves inherited stover even if it exceeds the next crop's $B_{\max}$. Growth and maintenance are integrated along $B(t)$ rather than taken as Euler fluxes.
- **ODE 5** reports `dh_dt_mm_day` as the effective mean rate $(H_1 - H_0)/\Delta t$, even when $H = 0$ is reached. The isolated runoff drag diagnostic integrates $X' = -\xi H_{\text{loss}} X$; when combined with other sources and losses, the full mass balance belongs to ODE 3.
- State variables $W$, NPK, $B$, and $H$, as well as harvest yield and stover residue, are not rounded during state propagation. Display layers may still round for presentation.

## Coupling

`advance_day` accepts `dt_days` (defaulting to one day). The coupling scheme is multiscale:

1. Hydrology, erosion, chemistry, and biomass use the slow state variables at step start.
2. Canopy temperature retains memory and is sub-integrated against frozen slow states and forcings. Each sub-step uses the PDF's thermal formulation.
3. Thermal sub-step size is capped at $0.5 \, C_p / (h + \lambda_{\gamma}\Delta)$, chosen numerically from local stiffness; Penman slope only estimates step size. Thermal relaxation stops once change is $\le 10^{-10}\text{ °C}$ under constant forcing.
4. Erosion rate passed to chemistry is divided by `dt_days`, delivering $\text{mm/day}$ rather than $\text{mm}$.
5. Water excess from soil-capacity reduction is added to `water_runoff_mm` and also reported as `capacity_runoff_mm`. Remaining water fluxes are reported in `water_infiltration_mm`, `water_etc_mm`, and `water_drainage_mm`.
6. Stover K recycling uses the exact mean transition biomass corresponding to stover actually decomposed over the interval.
7. Terminal $\psi$ uses the hydraulic thresholds computed from updated fertile soil depth.

The five-component state tuple contract is preserved. Its last element `history` accepts legacy scalar air temperatures as well as `(air_temp, canopy_temp)` pairs. This tuple preserves $T$ across steps without adding a sixth state element that would break adapters. The rotation API accepts both representations. Soil temperature remains an empirical proxy averaged from recent air history, not a measured observation or a separate soil thermal ODE.

Daily forcings do not capture hourly extremes. Thermal sub-stepping improves integration of those constant daily forcings without inventing sub-daily variability. The daily slow-state step remains a first-order approximation; `dt_days` allows refinement. The convergence test uses controlled synthetic conditions and does not guarantee universal accuracy for arbitrary forcings or step sizes.

## Reproducible Validation

Run `.venv/Scripts/python.exe -m pytest tests` on Windows. The `test_edo_pdf_regressions.py` suite checks the thermal solution, water and NPK mass balances, residue decay, zero maintenance, biomass fluxes, erosion bounds, thermal memory, and decreasing error across $1$, $1/2$, and $1/4$ day steps relative to a $1/128$-day reference.

Prices, botanical families, cycle durations, and catalog constants were left unchanged in that audit. Importing `gemini-code.json` and multi-harvest strawberry support are separate tasks. Parameter traceability (including root uptake and mineralization units), field validation, and analysis under real climate scenarios remain necessary before operational use.
