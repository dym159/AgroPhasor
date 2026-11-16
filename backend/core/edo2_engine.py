"""
Agrophysical Solver Engine for ODE 2: Root-Zone Water Balance (AgroPhasor).
Implements differential soil moisture dynamics, bare-soil evaporation, canopy transpiration,
topographic drainage, and irrigation alerts per AgroPhasor.pdf (Sections 3.2.2, 3.3, and 2.6.2).

Governing equation:
dW/dt = P0(t)*cos(theta) + eta_irrig*I(t) - ETc(T, W) - kd*sin(theta)*W
with physical bounds: 0 <= W(t) <= Wcc(H)
where any excess water above Wcc immediately becomes surface runoff.
"""

from dataclasses import dataclass, field
import math
from typing import List, Dict, Any, Optional, Tuple

from backend.core.physics import actual_vapor_pressure, saturation_vapor_pressure
from backend.models.crop_parameters import CropParameters, GLOBAL_CONSTANTS


@dataclass
class SoilHydraulicLimits:
    """Hydraulic limits of the effective root-zone profile from SSURGO/WSS and crop properties."""
    theta_fc: float       # Volumetric field capacity [m³/m³]
    theta_wp: float       # Volumetric wilting point [m³/m³]
    zr_mm: float          # Effective rooting depth Zr [mm]
    w_cc: float           # Field capacity water Wcc [mm]
    w_pmp: float          # Permanent wilting point Wpmp [mm]
    w_crit: float         # Critical water comfort threshold Wcrit [mm]
    raw: float            # Readily available water RAW = Wcc - Wcrit [mm]
    taw: float            # Total available water TAW = Wcc - Wpmp [mm]


@dataclass
class EDO2StepOutput:
    """Outputs of a single integration step dt of ODE 2."""
    soil_water_mm: float              # Soil moisture at step end W(t+dt) [mm]
    dw_dt: float                      # Net rate of change dW/dt [mm/day]
    etc_mm: float                     # Total evapotranspiration during step ETc [mm]
    transpiration_mm: float           # Canopy foliar transpiration [mm]
    evaporation_soil_mm: float        # Direct evaporation from shaded soil [mm]
    drainage_mm: float                # Hillslope gravitational drainage kd*sin(θ)*W [mm]
    runoff_mm: float                  # Surface runoff generated [mm]
    infiltration_mm: float            # Effective infiltration (rain + irrigation) [mm]
    gamma_c_relative: float           # Relative stomatal conductance factor γc / γmax [0, 1]
    vpd_kpa: float                    # Atmospheric vapor pressure deficit VPD [kPa]
    is_irrigation_needed: bool        # Operational alert: W <= Wcrit
    suggested_irrigation_mm: float    # Suggested replenishment irrigation depth [mm]
    is_drying_warning: bool           # Predictive fast-drying rate alert
    is_wilting: bool                  # Critical alert: W <= Wpmp (Red Shield)


def compute_soil_limits(
    crop: CropParameters,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    depth_mm: Optional[float] = None
) -> SoilHydraulicLimits:
    """Computes root-zone hydraulic limits for a given crop species."""
    zr = max(0.0, depth_mm) if depth_mm is not None else max(50.0, crop.Zr_mm)
    w_cc = theta_fc * zr
    w_pmp = theta_wp * zr
    p_dep = max(0.05, min(0.95, crop.p_depletion))
    w_crit = w_cc - p_dep * (w_cc - w_pmp)
    return SoilHydraulicLimits(
        theta_fc=theta_fc,
        theta_wp=theta_wp,
        zr_mm=zr,
        w_cc=round(w_cc, 2),
        w_pmp=round(w_pmp, 2),
        w_crit=round(w_crit, 2),
        raw=round(w_cc - w_crit, 2),
        taw=round(w_cc - w_pmp, 2)
    )


def relative_stomatal_conductance(w_mm: float, limits: SoilHydraulicLimits) -> float:
    """Relative stomatal opening fraction used in the daily ODE 2 balance."""
    if limits.w_cc <= 0:
        return 0.0
    if w_mm >= limits.w_crit:
        return 1.0
    span = max(1e-4, limits.w_crit - limits.w_pmp)
    return max(0.0, min(1.0, (w_mm - limits.w_pmp) / span))


def solve_edo2_step(
    w_current_mm: float,
    precip_mm: float,
    t_air_c: float,
    rh_pct: float,
    slope_deg: float,
    crop: CropParameters,
    irrigation_mm: float = 0.0,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    kd: float = 0.03,
    eta_irrigation: float = 0.85,
    e_suelo0: Optional[float] = None,
    lambda_b: Optional[float] = None,
    biomass_t_ha: Optional[float] = None,
    dt_days: float = 1.0,
    tau_warning_days: float = 2.0,
    is_crop: bool = True,
    depth_mm: Optional[float] = None,
    canopy_temp_c: Optional[float] = None
) -> EDO2StepOutput:
    """
    Integrates one time step dt of ODE 2 (Root-Zone Water Balance).
    
    Parameters:
    - w_current_mm: Root-zone moisture at step start [mm].
    - precip_mm: Incident precipitation P0(t) [mm/day].
    - t_air_c: Mean air temperature [°C].
    - rh_pct: Relative air humidity [%].
    - slope_deg: Terrain slope θ [degrees] (SRTM).
    - crop: Crop or vegetation cover parameter profile.
    - irrigation_mm: External irrigation depth I(t) [mm/day].
    - theta_fc: Volumetric field capacity (SSURGO/WSS).
    - theta_wp: Volumetric wilting point (SSURGO/WSS).
    - kd: Slope-dependent gravitational drainage coefficient.
    - eta_irrigation: Irrigation application efficiency (drip/sprinkler).
    - e_suelo0: Bare-soil basal evaporation (mm/day). Defaults to global constants.
    - lambda_b: Foliar light attenuation factor. Defaults to global constants.
    - biomass_t_ha: Parcel biomass for shading. Defaults to B_max or B0.
    - dt_days: Integration time step [days].
    - tau_warning_days: Look-ahead window for fast-drying alert [days].
    - is_crop: True if q(t)=Crop, False if q(t)=Transition (no transpiration).
    """
    if e_suelo0 is None:
        e_suelo0 = float(GLOBAL_CONSTANTS.get("E_suelo0_mm_dia", 4.2))
    if lambda_b is None:
        lambda_b = float(GLOBAL_CONSTANTS.get("lambda_B_ha_t", 0.45))
    if biomass_t_ha is None:
        biomass_t_ha = crop.B_max_t_ha if is_crop else crop.B0_t_ha

    limits = compute_soil_limits(crop, theta_fc, theta_wp, depth_mm)
    w_cc = limits.w_cc
    w_pmp = limits.w_pmp
    w_crit = limits.w_crit

    # 1. Slope trigonometry (SRTM)
    slope_rad = math.radians(max(0.0, min(80.0, slope_deg)))
    cos_theta = math.cos(slope_rad)
    sin_theta = math.sin(slope_rad)

    # 2. Atmospheric vapor pressure deficit VPD [kPa]
    ea_air = actual_vapor_pressure(t_air_c, rh_pct)
    es_air = saturation_vapor_pressure(t_air_c if canopy_temp_c is None else canopy_temp_c)
    vpd = max(0.0, es_air - ea_air)

    # 3. Stomatal conductance factor gamma_c(W) (AgroPhasor.pdf Sec. 3.3)
    eps = 1e-4
    gamma_rel = relative_stomatal_conductance(w_current_mm, limits) if is_crop and crop.gamma_max > 0 else 0.0

    # Daily effective conductance: gamma_max_daily [mm / (kPa · day)]
    # If gamma_max is in kg/(m²·s·kPa), multiply by 86400 s/day
    gamma_daily_max = crop.gamma_max * 86400.0 if crop.gamma_max < 0.1 else crop.gamma_max
    gamma_effective = gamma_daily_max * gamma_rel
    transpiration = gamma_effective * vpd

    # 4. Direct evaporation from biomass-shaded soil (Sec. 3.3)
    soil_wetness_ratio = max(0.0, min(1.0, w_current_mm / max(eps, w_cc)))
    canopy_shading = math.exp(-lambda_b * max(0.0, biomass_t_ha))
    evap_soil = e_suelo0 * soil_wetness_ratio * canopy_shading

    etc = transpiration + evap_soil

    # 5. Gravitational drainage and flux balance
    drainage = kd * sin_theta * max(0.0, w_current_mm)
    infil_precip = precip_mm * cos_theta
    infil_riego = eta_irrigation * max(0.0, irrigation_mm)
    total_infil = infil_precip + infil_riego

    dw_dt = total_infil - etc - drainage
    # Freeze stomatal conductance and biomass within the step. Evaporation
    # and drainage are linear in W, allowing an exponential update.
    loss_rate = kd * sin_theta + e_suelo0 * canopy_shading / max(eps, w_cc)
    source = total_infil - transpiration
    decay = math.exp(-loss_rate * dt_days)
    w_tentative = (w_current_mm * decay + source * (-math.expm1(-loss_rate * dt_days)) / loss_rate
                   if loss_rate > 0 else w_current_mm + source * dt_days)

    # 6. Saturation upper bound: clip at Wcc and convert overflow to surface runoff
    runoff = 0.0
    if w_tentative > w_cc:
        runoff = w_tentative - w_cc
        w_next = w_cc
    elif w_tentative < 0.0:
        w_next = 0.0
    else:
        w_next = w_tentative

    active_time = dt_days
    if w_tentative < 0 and source < 0 and loss_rate > 0:
        equilibrium = source / loss_rate
        active_time = math.log((w_current_mm - equilibrium) / -equilibrium) / loss_rate
    if loss_rate > 0:
        equilibrium = source / loss_rate
        water_integral = equilibrium * active_time + (w_current_mm - equilibrium) * (-math.expm1(-loss_rate * active_time)) / loss_rate
    else:
        water_integral = w_current_mm * active_time + .5 * source * active_time ** 2
    water_integral = max(0.0, water_integral)
    evaporation_total = e_suelo0 * canopy_shading / max(eps, w_cc) * water_integral
    drainage_total = kd * sin_theta * water_integral
    transpiration_total = transpiration * active_time
    # Water entering after exhaustion is consumed immediately by unmet demand.
    if active_time < dt_days:
        transpiration_total += total_infil * (dt_days - active_time)

    # 7. Diagnostics and Operational Alerts Layer (Sec. 2.6.2)
    is_irrigation = w_next <= w_crit
    is_wilting = w_next <= w_pmp
    suggested_irrigation = round(max(0.0, (w_cc - w_next) / max(eps, eta_irrigation)), 2) if is_irrigation else 0.0
    
    # Look-ahead fast-drying alert: W + tau * (dW/dt) <= Wcrit
    projected_w = w_next + tau_warning_days * dw_dt
    is_drying_alert = projected_w <= w_crit

    return EDO2StepOutput(
        soil_water_mm=round(w_next, 2),
        dw_dt=round(dw_dt, 3),
        etc_mm=round(transpiration_total + evaporation_total, 3),
        transpiration_mm=round(transpiration_total, 3),
        evaporation_soil_mm=round(evaporation_total, 3),
        drainage_mm=round(drainage_total, 3),
        runoff_mm=round(runoff, 3),
        infiltration_mm=round(total_infil * dt_days, 3),
        gamma_c_relative=round(gamma_rel, 3),
        vpd_kpa=round(vpd, 3),
        is_irrigation_needed=is_irrigation,
        suggested_irrigation_mm=suggested_irrigation,
        is_drying_warning=is_drying_alert,
        is_wilting=is_wilting
    )


def simulate_edo2_timeseries(
    precip_series: List[float],
    t_air_series: List[float],
    rh_series: List[float],
    crop: CropParameters,
    slope_deg: float = 0.0,
    w0_mm: Optional[float] = None,
    smap_root_wetness: Optional[float] = None,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    auto_irrigate: bool = False,
    eta_irrigation: float = 0.85,
    dt_days: float = 1.0,
    is_crop: bool = True
) -> Dict[str, Any]:
    """
    Runs a complete ODE 2 time-series simulation over a climate sequence.
    
    Compares rainfed farming (auto_irrigate=False) against automated smart irrigation
    (auto_irrigate=True), recording all state trajectories and water balances.
    """
    n_steps = len(precip_series)
    if not (len(t_air_series) == n_steps and len(rh_series) == n_steps):
        raise ValueError("Weather series (precip, t_air, rh) must have the same length.")

    limits = compute_soil_limits(crop, theta_fc, theta_wp)
    w_cc = limits.w_cc
    w_pmp = limits.w_pmp
    w_crit = limits.w_crit

    # Initialize W(0)
    if w0_mm is not None:
        current_w = max(0.0, min(w_cc, float(w0_mm)))
    elif smap_root_wetness is not None:
        wetness = max(0.0, min(1.0, float(smap_root_wetness)))
        current_w = w_pmp + wetness * (w_cc - w_pmp)
    else:
        # Default to critical comfort threshold
        current_w = w_crit

    w_series = [round(current_w, 2)]
    etc_series = []
    transp_series = []
    evap_series = []
    drainage_series = []
    runoff_series = []
    irrigation_series = []
    irrigation_events: List[Dict[str, Any]] = []
    gamma_rel_series = []
    stress_days = 0
    wilting_days = 0

    for step in range(n_steps):
        p0 = precip_series[step]
        t_air = t_air_series[step]
        rh = rh_series[step]

        applied_irrigation = 0.0
        if auto_irrigate and current_w <= w_crit:
            applied_irrigation = (w_cc - current_w) / eta_irrigation
            irrigation_events.append({
                "step": step,
                "w_before_mm": round(current_w, 2),
                "irrigation_applied_mm": round(applied_irrigation, 2)
            })

        step_res = solve_edo2_step(
            w_current_mm=current_w,
            precip_mm=p0,
            t_air_c=t_air,
            rh_pct=rh,
            slope_deg=slope_deg,
            crop=crop,
            irrigation_mm=applied_irrigation,
            theta_fc=theta_fc,
            theta_wp=theta_wp,
            eta_irrigation=eta_irrigation,
            dt_days=dt_days,
            is_crop=is_crop
        )

        current_w = step_res.soil_water_mm
        w_series.append(current_w)
        etc_series.append(step_res.etc_mm)
        transp_series.append(step_res.transpiration_mm)
        evap_series.append(step_res.evaporation_soil_mm)
        drainage_series.append(step_res.drainage_mm)
        runoff_series.append(step_res.runoff_mm)
        irrigation_series.append(round(applied_irrigation, 2))
        gamma_rel_series.append(step_res.gamma_c_relative)

        if current_w <= w_crit:
            stress_days += 1
        if current_w <= w_pmp:
            wilting_days += 1

    return {
        "crop": crop.name,
        "limits": {
            "W_cc_mm": w_cc,
            "W_pmp_mm": w_pmp,
            "W_crit_mm": w_crit,
            "RAW_mm": limits.raw,
            "TAW_mm": limits.taw
        },
        "soil_water_series": w_series,
        "etc_series": etc_series,
        "transpiration_series": transp_series,
        "soil_evaporation_series": evap_series,
        "drainage_series": drainage_series,
        "runoff_series": runoff_series,
        "irrigation_applied_series": irrigation_series,
        "gamma_c_relative_series": gamma_rel_series,
        "summary": {
            "total_precip_mm": round(sum(precip_series), 2),
            "total_irrigation_mm": round(sum(irrigation_series), 2),
            "total_etc_mm": round(sum(etc_series), 2),
            "total_drainage_mm": round(sum(drainage_series), 2),
            "total_runoff_mm": round(sum(runoff_series), 2),
            "final_soil_water_mm": current_w,
            "min_soil_water_mm": min(w_series),
            "max_soil_water_mm": max(w_series),
            "stress_days": stress_days,
            "wilting_days": wilting_days,
            "irrigation_events_count": len(irrigation_events),
            "irrigation_events": irrigation_events
        }
    }
