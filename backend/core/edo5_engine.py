"""
Agrophysical Solver Engine for ODE 5: Topsoil Water Erosion (AgroPhasor).
Models irreversible organic horizon wear caused by rainfall on unprotected hillslopes,
coupled with SRTM topography, GPM/IMERG/NASA POWER precipitation, Landsat/MODIS/ODE4 vegetation cover,
SSURGO/WSS soil parameters, and Pareto soil conservation metric f2.

Governing differential equation (AgroPhasor.pdf, Sec. 3.2.5):
    dH_i,j / dt = - k_er(q) * P_0(t) * sin(theta_i,j) * exp(-lambda_B * B_i,j(t))

Exact analytical step update for time step dt (Sec. 3.2.5):
    H_i,j(t + dt) = max(0, H_i,j(t) - k_er(q) * P_0(t) * sin(theta_i,j) * exp(-lambda_B * B_i,j(t)) * dt)

Physical and geometric bounds:
    0 <= H_i,j(t) <= H_i,j(0)
    dH / dt <= 0 (irreversible process on a seasonal scale)
"""

from dataclasses import dataclass, field
import math
from typing import List, Dict, Any, Optional, Tuple, Union

from backend.models.crop_parameters import CropParameters, GLOBAL_CONSTANTS


@dataclass
class EDO5StepOutput:
    """Physical outputs of a single ODE 5 integration step dt."""
    h_current_mm: float                 # Current fertile horizon depth H(t+dt) [mm]
    h_initial_mm: float                 # Original fertile depth H(0) [mm]
    dh_dt_mm_day: float                 # Instantaneous erosion rate dH/dt <= 0 [mm/day]
    erosion_loss_step_mm: float         # Soil loss during step Delta_H [mm]
    accumulated_erosion_mm: float       # Cumulative total loss H(0) - H(t) [mm]
    soil_retention_ratio: float         # Retained soil fraction H(t)/H(0) in [0, 1]
    topographic_slope_deg: float        # Topographic slope theta [degrees] (SRTM)
    topographic_factor_sin: float       # Geometric modulator sin(theta) [0, 1]
    vegetation_cover_factor: float      # Attenuation term exp(-lambda_B * B) in (0, 1]
    erodibility_k_er: float             # Active erodibility coefficient k_er(q)
    is_transition_mode: bool            # True if q=Transition (tillage), False if crop
    # Couplings with other agrophysical subsystems
    w_cc_mm: float                      # Updated field capacity W_cc(H) = theta_fc * H [mm] (ODE 2)
    w_pmp_mm: float                     # Updated wilting point W_pmp(H) = theta_wp * H [mm] (ODE 2)
    nutrient_drag_kg_ha: Dict[str, float] # N-P-K runoff drag loss [kg/ha/day] (ODE 3)
    # Coupling with 3D / WebGL visual engine
    mesh_subsidence_m: float            # 3D mesh geometric subsidence [m]
    soil_color_rgb: Tuple[int, int, int] # Interpolated soil color (Brown -> Bedrock Gray)
    is_bedrock_exposed: bool            # Critical alert: H <= 0.05 mm (bedrock exposed)


def compute_soil_color(
    retention_ratio: float
) -> Tuple[int, int, int]:
    """
    Interpolates terrain color for the 3D interface (AgroPhasor.pdf Sec. 2.6.1):
    - retention_ratio = 1.0 (Intact soil): Fertile organic brown (101, 67, 33)
    - retention_ratio = 0.0 (Fully eroded soil): Bedrock gray (128, 128, 128)
    """
    ratio = max(0.0, min(1.0, retention_ratio))
    r = int(round(128.0 + (101.0 - 128.0) * ratio))
    g = int(round(128.0 + (67.0 - 128.0) * ratio))
    b = int(round(128.0 + (33.0 - 128.0) * ratio))
    return (r, g, b)


def solve_edo5_step(
    h_current_mm: float,
    precip_mm: float,
    slope_deg: float,
    biomass_t_ha: float,
    is_transition: bool = False,
    h_initial_mm: Optional[float] = None,
    k_er_cultivo: Optional[float] = None,
    k_er_labranza: Optional[float] = None,
    lambda_b: Optional[float] = None,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    current_nutrients_kg_ha: Optional[Dict[str, float]] = None,
    xi_n: Optional[float] = None,
    xi_p: Optional[float] = None,
    xi_k: Optional[float] = None,
    dt_days: float = 1.0,
    kappa_er: float = 0.001
) -> EDO5StepOutput:
    """
    Analytically solves one time step dt of ODE 5:
    
    dH/dt = - k_er(q) * P_0(t) * sin(theta) * exp(-lambda_B * B(t))
    H(t + dt) = max(0, H(t) + (dH/dt) * dt)
    
    Parameters:
    - h_current_mm: Current fertile horizon depth [mm] (0 <= H <= H0).
    - precip_mm: Daily total precipitation P_0(t) [mm/day] (GPM / IMERG / NASA POWER).
    - slope_deg: Terrain slope theta [degrees] (SRTM).
    - biomass_t_ha: Protective plant biomass or stover B(t) [t/ha] (ODE 4 / Landsat).
    - is_transition: True if parcel is in fallow/tillage (q = Transition).
    - h_initial_mm: Original baseline fertile depth H(0) [mm] (SSURGO / WSS).
    - theta_fc: Volumetric water content at field capacity (m³/m³).
    - theta_wp: Volumetric water content at wilting point (m³/m³).
    - current_nutrients_kg_ha: Current [N, P, K] vector to compute mechanical drag.
    - kappa_er: Visual scale factor for 3D mesh subsidence [m/mm].
    """
    # 1. Load agrophysical constants
    if k_er_cultivo is None:
        k_er_cultivo = float(GLOBAL_CONSTANTS.get("k_er_cultivo", 0.0004))
    if k_er_labranza is None:
        k_er_labranza = float(GLOBAL_CONSTANTS.get("k_er_labranza", 0.0035))
    if lambda_b is None:
        lambda_b = float(GLOBAL_CONSTANTS.get("lambda_B_ha_t", 0.45))
    if xi_n is None:
        xi_n = float(GLOBAL_CONSTANTS.get("xi_N", 0.004))
    if xi_p is None:
        xi_p = float(GLOBAL_CONSTANTS.get("xi_P", 0.008))
    if xi_k is None:
        xi_k = float(GLOBAL_CONSTANTS.get("xi_K", 0.003))

    h0 = h_initial_mm if h_initial_mm is not None else max(1.0, h_current_mm)

    # When no fertile topsoil remains, erosion drops to zero
    if h_current_mm <= 0.0:
        return EDO5StepOutput(
            h_current_mm=0.0,
            h_initial_mm=h0,
            dh_dt_mm_day=0.0,
            erosion_loss_step_mm=0.0,
            accumulated_erosion_mm=h0,
            soil_retention_ratio=0.0,
            topographic_slope_deg=slope_deg,
            topographic_factor_sin=math.sin(math.radians(max(0.0, min(85.0, slope_deg)))),
            vegetation_cover_factor=math.exp(-lambda_b * max(0.0, biomass_t_ha)),
            erodibility_k_er=k_er_labranza if is_transition else k_er_cultivo,
            is_transition_mode=is_transition,
            w_cc_mm=0.0,
            w_pmp_mm=0.0,
            nutrient_drag_kg_ha={"N": 0.0, "P": 0.0, "K": 0.0},
            mesh_subsidence_m=round(kappa_er * h0, 4),
            soil_color_rgb=(128, 128, 128),
            is_bedrock_exposed=True
        )

    # 2. SRTM topographic modulator: sin(theta)
    clamped_slope = max(0.0, min(85.0, slope_deg))
    slope_rad = math.radians(clamped_slope)
    sin_theta = math.sin(slope_rad)

    # 3. Vegetation modulator (Canopy + stover biomass): exp(-lambda_B * B)
    clamped_biomass = max(0.0, biomass_t_ha)
    veg_cover = math.exp(-lambda_b * clamped_biomass)

    # 4. Operating mode q(t): erodibility
    k_er = k_er_labranza if is_transition else k_er_cultivo

    # 5. Effective precipitation
    p0 = max(0.0, precip_mm)

    # 6. ODE 5 evaluation
    # Instantaneous erosion rate: dH/dt <= 0
    erosion_rate = k_er * p0 * sin_theta * veg_cover
    dh_dt = -erosion_rate

    # Integrated analytical step
    loss_step = erosion_rate * dt_days
    # Cannot erode more soil than currently remains
    effective_loss = min(h_current_mm, loss_step)
    h_next = max(0.0, h_current_mm - effective_loss)

    accumulated_loss = max(0.0, h0 - h_next)
    retention_ratio = h_next / h0 if h0 > 0.0 else 0.0

    # 7. Soil physical feedback to ODE 2
    w_cc_updated = round(theta_fc * h_next, 2)
    w_pmp_updated = round(theta_wp * h_next, 2)

    # 8. Biogeochemical feedback to ODE 3 (nutrient runoff drag)
    nut_drag = {"N": 0.0, "P": 0.0, "K": 0.0}
    if current_nutrients_kg_ha is not None:
        n_curr = max(0.0, current_nutrients_kg_ha.get("N", 0.0))
        p_curr = max(0.0, current_nutrients_kg_ha.get("P", 0.0))
        k_curr = max(0.0, current_nutrients_kg_ha.get("K", 0.0))
        # Loss proportional to organic horizon wear: xi * |dH/dt| * Nutrient
        nut_drag["N"] = round(xi_n * effective_loss * n_curr, 4)
        nut_drag["P"] = round(xi_p * effective_loss * p_curr, 4)
        nut_drag["K"] = round(xi_k * effective_loss * k_curr, 4)

    # 9. 3D WebGL visual layer
    mesh_subsidence = round(kappa_er * accumulated_loss, 4)
    soil_color = compute_soil_color(retention_ratio)
    is_bedrock = h_next <= 0.05

    return EDO5StepOutput(
        h_current_mm=round(h_next, 4),
        h_initial_mm=round(h0, 4),
        dh_dt_mm_day=round(dh_dt, 6),
        erosion_loss_step_mm=round(effective_loss, 6),
        accumulated_erosion_mm=round(accumulated_loss, 4),
        soil_retention_ratio=round(retention_ratio, 4),
        topographic_slope_deg=clamped_slope,
        topographic_factor_sin=round(sin_theta, 4),
        vegetation_cover_factor=round(veg_cover, 4),
        erodibility_k_er=k_er,
        is_transition_mode=is_transition,
        w_cc_mm=w_cc_updated,
        w_pmp_mm=w_pmp_updated,
        nutrient_drag_kg_ha=nut_drag,
        mesh_subsidence_m=mesh_subsidence,
        soil_color_rgb=soil_color,
        is_bedrock_exposed=is_bedrock
    )


def simulate_edo5_timeseries(
    precip_series: List[float],
    slope_deg: float,
    biomass_series: List[float],
    transition_flags: List[bool],
    h0_mm: float = 400.0,
    k_er_cultivo: Optional[float] = None,
    k_er_labranza: Optional[float] = None,
    lambda_b: Optional[float] = None,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    initial_nutrients_kg_ha: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Runs a full ODE 5 time-series simulation over an N-day trajectory.
    """
    n_days = len(precip_series)
    if len(biomass_series) != n_days or len(transition_flags) != n_days:
        raise ValueError("Precipitation, biomass, and transition flag series must have the same length.")

    h_history: List[float] = []
    loss_history: List[float] = []
    w_cc_history: List[float] = []
    cover_history: List[float] = []
    p_drag_total = 0.0

    current_h = h0_mm
    current_nutrients = dict(initial_nutrients_kg_ha) if initial_nutrients_kg_ha else {"N": 100.0, "P": 40.0, "K": 120.0}

    for day in range(n_days):
        precip = precip_series[day]
        biomass = biomass_series[day]
        is_trans = transition_flags[day]

        step = solve_edo5_step(
            h_current_mm=current_h,
            precip_mm=precip,
            slope_deg=slope_deg,
            biomass_t_ha=biomass,
            is_transition=is_trans,
            h_initial_mm=h0_mm,
            k_er_cultivo=k_er_cultivo,
            k_er_labranza=k_er_labranza,
            lambda_b=lambda_b,
            theta_fc=theta_fc,
            theta_wp=theta_wp,
            current_nutrients_kg_ha=current_nutrients
        )

        h_history.append(step.h_current_mm)
        loss_history.append(step.erosion_loss_step_mm)
        w_cc_history.append(step.w_cc_mm)
        cover_history.append(step.vegetation_cover_factor)
        p_drag_total += step.nutrient_drag_kg_ha.get("P", 0.0)

        # Update internal state
        current_h = step.h_current_mm
        current_nutrients["N"] = max(0.0, current_nutrients["N"] - step.nutrient_drag_kg_ha.get("N", 0.0))
        current_nutrients["P"] = max(0.0, current_nutrients["P"] - step.nutrient_drag_kg_ha.get("P", 0.0))
        current_nutrients["K"] = max(0.0, current_nutrients["K"] - step.nutrient_drag_kg_ha.get("K", 0.0))

    accumulated_loss = round(h0_mm - current_h, 4)
    loss_fraction = round(accumulated_loss / h0_mm, 5) if h0_mm > 0 else 0.0

    return {
        "days": n_days,
        "h0_mm": h0_mm,
        "final_h_mm": round(current_h, 4),
        "total_erosion_loss_mm": accumulated_loss,
        "erosion_loss_pct": round(loss_fraction * 100.0, 3),
        "final_w_cc_mm": round(theta_fc * current_h, 2),
        "initial_w_cc_mm": round(theta_fc * h0_mm, 2),
        "cumulative_p_drag_kg_ha": round(p_drag_total, 4),
        "trajectory_h": h_history,
        "trajectory_loss": loss_history,
        "trajectory_w_cc": w_cc_history,
        "trajectory_cover": cover_history
    }


def compute_soil_pareto_metric_f2(
    h_initial: float,
    h_final: float,
    chemical_health_eta_n: float,
    omega_h: float = 0.5,
    omega_n: float = 0.5
) -> float:
    """
    Computes Pareto Front metric f2 (AgroPhasor.pdf, Sec. 3.5, Eq. 3):
    
    f2(pi) = omega_H * [ (H(0) - H(T)) / H(0) ] + omega_N * [ 1 - eta_N(T) ]
    
    Where:
    - (H(0) - H(T)) / H(0): Fraction of fertile soil lost to hillslope water erosion.
    - 1 - eta_N(T): Final chemical fertility deficit per Liebig's Law.
    """
    h0 = max(1e-4, h_initial)
    delta_h_rel = max(0.0, min(1.0, (h0 - h_final) / h0))
    nutrient_deficit = max(0.0, min(1.0, 1.0 - chemical_health_eta_n))
    f2 = omega_h * delta_h_rel + omega_n * nutrient_deficit
    return round(f2, 4)
