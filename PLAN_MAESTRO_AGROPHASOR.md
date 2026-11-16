# AgroPhasor Master Plan

## Project Deliverable

A web application where a farmer can draw their parcel, build a crop calendar, simulate how the land responds, and compare their plan against recommended crop rotations. The target user knows their land and relies on a mobile phone for day-to-day work. The interface must be usable with brief instructions, familiar terminology, and touch-friendly controls.

The initial release demonstrates one parcel, two or more planting periods, and a focused crop catalog agreed upon with the Physics team. Starting with one crop per parcel and enabling up to two management zones once the simulator and UI pass single-parcel validation, both the calendar and rotation selector are designed to work across mobile and desktop.

## Work Sequence

| Milestone | Parallel Workstreams | Completion Evidence |
|---|---|---|
| 1. Lock the API Contract | Physics locks units, parameters, and reference cases. Math designs numerical integration and objective metrics. CS prepares the map, calendar, and API with mock fixtures. | Versioned request/response examples with one parcel and two periods. Every team knows its exact inputs and outputs. |
| 2. Solve the Minimal Case | Physics and Math verify a single cell and discrete harvest/planting transitions. CS integrates NASA POWER, tests the visual workflow, and prepares deployment. | Reproducible baseline and stress test cases with reference outputs per state variable and tolerances. |
| 3. Integrate Crop Rotation | CS connects the per-cell engine and period-level results. Math verifies the search algorithm and Pareto front. | End-to-end user flow comparing a manual planting plan against engine-driven rotation recommendations. |
| 4. Validate and Publish | The team runs scientific, API, UI, and performance tests. A representative target user tests the interface. | Deployed demo, attributed data sources, reproducible results, and verified fallback workflow. |
| 5. Pilot Adoption | Following the demo, prepare a field pilot with a cooperative or agricultural technician managing multiple parcels. | Evidence of real planting decisions informed by the tool and willingness to pay for recurring campaigns. |

## Physics · Defining Land Behavior

1. **Lock per-cell state variables.** Use canopy temperature `T` (°C), root-zone soil moisture `W` (mm), available nutrients `N, P, K` (kg/ha), above-ground biomass `B` (t/ha), and fertile topsoil depth `H` (mm). These form five physical blocks and seven scalar components. Document initial conditions, units, valid bounds, and the decoupled 2.5D column hypothesis, clearly distinguishing observed data, estimates, and assumptions.
2. **Close the conservation balances.** Deliver the approved equations for thermal energy, water, nutrients, biomass, and erosion, along with the closure relations from the technical PDF. For each term, specify its meaning, unit, sign, range, source, and tunable parameter. Clarify which inputs represent farmer management—irrigation, fertilization, and stover retention—and which describe terrain properties or hypothetical climate scenarios.
3. **Resolve discrete transitions.** At harvest, record yield via the harvest index, compute remaining stover residue, and activate the bare-soil/fallow transition regime. At planting, initialize basal biomass and load the next crop's parameters. Define how organic matter incorporated at planting is accounted for, which state variables carry over across periods, and how green biomass vs. stover residue differently protect against erosion during transitions.
4. **Deliver the initial crop catalog.** For each crop, record botanical family, cycle duration, planting window, stage coefficients and thresholds, basal and maximum biomass, and harvest index. Define hard feasibility constraints versus advisory risk warnings, including agronomic rules such as family alternation.
5. **Finalize explainable outputs.** Define the environmental shield index, soil moisture status, heat stress, fertility sufficiency, biomass growth, topsoil erosion, and irrigation alerts. For each indicator, agree on its formula, units, threshold, spatial aggregation scale, and farmer-facing label, marking model outputs as estimates.
6. **Provide reference test cases.** Supply one cell under baseline conditions and another under climate stress, including expected inputs, outputs, and a harvest-to-planting transition, plus a sloped rainfall case with varying cover. Validate orders of magnitude, conservation balances, and agronomic plausibility.

## Mathematics · Turning the Model into Verifiable Computation

1. **Specify the hybrid dynamical system.** Lock the discrete crop vs. transition mode, date semantics, and event update ordering. Document which couplings update at each time step and the hypotheses underlying the matrix exponential integrator for NPK. Select the numerical integrator, step size, and tolerances for the remaining equations, verifying convergence and unconditional non-negativity.
2. **Verify climate scenarios.** Prepare a historical baseline and stress scenarios with explicit assumptions. When using FFT/Fourier series plus stochastic perturbations, document the fitting window, random seed, and construction of precipitation and temperature series, verifying seasonality, magnitude, and extreme persistence.
3. **Define the rotation optimization problem.** A candidate rotation comprises crops, planting/harvest dates, transition intervals, and inherited parcel state. Incorporate farmer-fixed crops, cycle durations, and feasibility rules, specifying whether threshold violations invalidate a candidate or raise warnings, and what the engine returns when all candidates are infeasible.
4. **Close the four objective metrics.** Document how environmental/water stress (`w1`), soil degradation (`w2`), economic deficit (`w3`), and cycle payback time (`w4`) are minimized. Agree on spatial and temporal aggregation, min-max normalization bounds, handling of constant metrics, tie-breaking rules, and net margin vs. gross revenue fallback when regional production costs are omitted.
5. **Verify search and Pareto optimality.** Enumerate the pilot catalog to obtain an exact reference Pareto front, verifying feasibility filtering, objective bounds, and non-dominated candidates.
6. **Lock priority weights.** Provide non-negative weights summing to one for **Maximum Resilience**, **Optimal Balance**, and **Maximum Yield / Profit**. Moving the priority knobs re-ranks already-simulated Pareto candidates instantaneously without re-running the ODE engine.

## Computer Science (CS) · Bringing It to the Web

| Workstream | Scope & Deliverable | Linear |
|---|---|---|
| Repository & Environment | Git hooks, configuration and secret protection, reproducible environment, and PR CI checks. | [CC-01](https://linear.app/nasa-challengue-tasks/issue/NAS-6), [CC-11](https://linear.app/nasa-challengue-tasks/issue/NAS-16), [CC-13](https://linear.app/nasa-challengue-tasks/issue/NAS-18) |
| API Contract | Validate GeoJSON, parcel geometry, and dates; define parcels, periods, and fixed crops; link simulation outputs, alerts, and events to periods; test missing data, invalid geometry, and infeasible rotations. | [CC-02](https://linear.app/nasa-challengue-tasks/issue/NAS-7), [CC-05](https://linear.app/nasa-challengue-tasks/issue/NAS-10) |
| Data Integration | Integrate NASA POWER with cached fallback for reproducibility, SRTM v3 for elevation/slope/aspect, SMAP root-zone moisture initialization, and MIDAGRI regional farm-gate prices. | [CC-06](https://linear.app/nasa-challengue-tasks/issue/NAS-11), [CC-14](https://linear.app/nasa-challengue-tasks/issue/NAS-19), [CC-15](https://linear.app/nasa-challengue-tasks/issue/NAS-20) |
| Simulation Engine | Implement per-cell ODE integration, discrete harvest/planting events, climate scenarios, and spatial aggregation matching Physics and Math reference cases. | [CC-07](https://linear.app/nasa-challengue-tasks/issue/NAS-12) |
| Map & Parcels | Satellite map, optional geolocation, and touch-friendly polygon drawing, editing, and confirmation, with manual search/navigation fallback when geolocation is denied. | [CC-03](https://linear.app/nasa-challengue-tasks/issue/NAS-8), [CC-04](https://linear.app/nasa-challengue-tasks/issue/NAS-9) |
| Rotation Planning | Crop assignment, multi-phase calendar, date simulation, rotation comparison, and explicit application of recommended routes to the timeline. | [CC-09](https://linear.app/nasa-challengue-tasks/issue/NAS-14) |
| Dashboard & 3D Viewer | Connect the active period to parcel state, 2.5D/3D terrain & Lissajous shield viewer, and priority knobs that re-rank routes without repeating physical simulation. | [CC-08](https://linear.app/nasa-challengue-tasks/issue/NAS-13), [CC-20](https://linear.app/nasa-challengue-tasks/issue/NAS-25), [CC-21](https://linear.app/nasa-challengue-tasks/issue/NAS-26) |
| Testing & Deployment | Verify API, ODE engines, optimizer, and UI workflow; deploy demo and validate cold/warm cache behavior. | [CC-10](https://linear.app/nasa-challengue-tasks/issue/NAS-15), [CC-12](https://linear.app/nasa-challengue-tasks/issue/NAS-17) |

### Farmer User Journey

1. **Draw Your Parcel:** Draw or edit the parcel boundary on the satellite map and confirm its shape.
2. **Build Your Calendar:** Below the terrain view, the timeline displays monthly ticks (**Jan · Feb · Mar**) and planting phases (`+ Phase`), each with its start and estimated harvest dates.
3. **Select Your Crops:** Use the top-right crop catalog to filter, select, or drag crops onto timeline phases.
4. **Inspect Your Parcel:** The center stage renders the 2.5D/3D terrain and 24-hour thermal shield, while the left column provides strategy presets and priority knobs (`w1`–`w4`).
5. **Compare and Decide:** The bottom-right panel displays the recommended crop rotation sequence, agronomic/economic metrics, and comparison against the current timeline plan, with an explicit **Apply to timeline** action.

### Release Verification Checklist

- [x] Physics equations, parameters, and tolerances implemented and verified across baseline and stress test cases (`test_edo1_engine.py`–`test_edo5_engine.py`).
- [x] Multi-period engine tests verify harvest jumps, stover transition, and planting carryover of moisture, nutrients, and fertile topsoil depth (`test_pdf_integration.py`).
- [x] Pilot crop catalog reproduces the Pareto front, discards thermally infeasible sequences, and handles missing regional costs/prices (`test_rotation_ranking.py`, `test_rotation_service.py`).
- [x] Changing a strategy preset or priority knob (`w1`–`w4`) instantaneously re-ranks evaluated candidates without re-running the ODE simulation (`test_rotation_ranking.mjs`).
- [ ] Field usability test with a target farmer on mobile.
- [x] Demo attributes observed NASA POWER / SRTM / MIDAGRI sources and clearly labels model estimates and assumptions.

## Pilot & Business Model

Validate a per-campaign licensing model with an agricultural cooperative, tiered by active parcels. The cooperative subscribes, an agronomist supports onboarding, and farmers build or review their planting calendars, comparing their habitual rotation against Pareto-optimized alternatives.

## References

- [AgroPhasor Technical Specification (PDF)](Agrophasor.pdf), especially §§2.6 and 3–8.
- [AgroPhasor · CS Project in Linear](https://linear.app/nasa-challengue-tasks/project/agrophasor-cc-bc98b7d10b09).
