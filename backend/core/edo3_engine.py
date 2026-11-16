"""
Agrophysical Solver Engine for ODE 3: Macronutrient Vector Dynamics (AgroPhasor).
Implements the continuous evolution of N_i,j(t) = [N, P, K]^T in kg/ha per AgroPhasor.pdf
(Sections 3.2.3, 3.3, 1.2, 1.3, and 2.5).

Component-wise decoupled linear matrix ODE:
    d N_i,j / dt = S_N,i,j(t) - Lambda_N,i,j(t) * N_i,j(t)

Exact unconditionally non-negative analytical solution:
    N_i,j(t + dt) = exp(-Lambda * dt) * N_i,j(t) + dt * phi_1(Lambda * dt) * S
    with phi_1(z) = (1 - exp(-z)) / z
"""

from dataclasses import dataclass, field
import math
from typing import Dict, Any, List, Optional, Tuple, Union

from backend.models.crop_parameters import CropParameters, GLOBAL_CONSTANTS


@dataclass
class SoilChemicalProperties:
    """Basal soil chemical properties (SSURGO / WSS / GAEZ)."""
    om_pct: float = 3.0            # Initial organic matter OM [%]
    cic_cmolc_kg: float = 22.0     # Cation Exchange Capacity (CEC) [cmol_c/kg]
    ph: float = 6.8                # Surface soil pH [dimensionless]
    ec_ds_m: float = 0.8           # Electrical conductivity (salinity) [dS/m]
    phi_ph_ec: float = 1.0         # Chemical availability modulator phi_pH,EC [0, 1]


@dataclass
class EDO3StepOutput:
    """Outputs of a single integration step dt of ODE 3."""
    n_kg_ha: float                 # Available Nitrogen N [kg/ha]
    p_kg_ha: float                 # Available Phosphorus P [kg/ha]
    k_kg_ha: float                 # Available Potassium K [kg/ha]
    dn_dt: float                   # Rate of change dN/dt [kg/(ha·day)]
    dp_dt: float                   # Rate of change dP/dt [kg/(ha·day)]
    dk_dt: float                   # Rate of change dK/dt [kg/(ha·day)]
    eta_nutrientes: float          # Global Liebig nutrient efficiency [0, 1]
    limiting_nutrient: str         # Limiting macronutrient ("N", "P", or "K")
    eta_components: Dict[str, float]  # Partial Liebig factors (eta_N, eta_P, eta_K)
    biological_n_fixation_kg: float   # Biological N fixation input in step [kg/ha]
    p_solubilization_kg: float        # Root P solubilization input in step [kg/ha]
    k_stover_recycling_kg: float      # Stover decomposition K input in step [kg/ha]
    leaching_n_kg: float              # Vertical N leaching loss [kg/ha]
    leaching_k_kg: float              # Vertical K leaching loss [kg/ha]
    erosion_loss_p_kg: float          # Eroded-soil particulate P loss [kg/ha]
    f_t_microbial: float              # Microbial thermal Q10 factor [dimensionless]


def calculate_phi_ph_ec(ph: float, ec: float) -> float:
    """
    Computes the chemical availability modulator phi_pH,EC in [0, 1].
    - Optimal pH range: 6.0 - 7.5. Strongly acidic or alkaline soils reduce availability.
    - Salinity EC > 1.5 dS/m induces osmotic stress and inhibits root uptake.
    """
    if 6.0 <= ph <= 7.5:
        f_ph = 1.0
    elif ph < 6.0:
        f_ph = max(0.20, 1.0 - 0.25 * math.pow(max(0.0, 6.0 - ph), 1.5))
    else:
        f_ph = max(0.30, 1.0 - 0.20 * math.pow(max(0.0, ph - 7.5), 1.5))

    if ec <= 1.5:
        f_ec = 1.0
    else:
        f_ec = max(0.10, 1.0 - 0.15 * (ec - 1.5))

    return round(float(max(0.0, min(1.0, f_ph * f_ec))), 3)


def microbial_temperature_factor(t_soil_c: float, q10: float = 2.0) -> float:
    """Microbial and enzymatic Q10 kinetics centered at 20 °C."""
    return float(math.pow(q10, (t_soil_c - 20.0) / 10.0))


def phi1(z: float) -> float:
    """
    Auxiliary function phi_1(z) = (1 - exp(-z)) / z.
    Singularity-free as z -> 0 via Taylor expansion.
    """
    if abs(z) < 1e-6:
        return 1.0 - 0.5 * z + (z * z) / 6.0
    return (1.0 - math.exp(-z)) / z


def compute_liebig_factor(
    n_kg_ha: float,
    p_kg_ha: float,
    k_kg_ha: float,
    kn: float = 35.0,
    kp: float = 18.0,
    kk: float = 45.0
) -> Tuple[float, str, Dict[str, float]]:
    """
    Scalar projection via Liebig's Law of the Minimum (PDF Sec. 1.2 and 3.3):
    eta_nutrientes = min( N/(N + KN), P/(P + KP), K/(K + KK) ) in [0, 1]
    """
    n_val = max(0.0, n_kg_ha)
    p_val = max(0.0, p_kg_ha)
    k_val = max(0.0, k_kg_ha)

    e_n = n_val / (n_val + kn) if (n_val + kn) > 0 else 0.0
    e_p = p_val / (p_val + kp) if (p_val + kp) > 0 else 0.0
    e_k = k_val / (k_val + kk) if (k_val + kk) > 0 else 0.0

    eta_min = min(e_n, e_p, e_k)
    if eta_min == e_n:
        limiting = "N"
    elif eta_min == e_p:
        limiting = "P"
    else:
        limiting = "K"

    components = {
        "eta_N": round(e_n, 3),
        "eta_P": round(e_p, 3),
        "eta_K": round(e_k, 3)
    }
    return round(eta_min, 3), limiting, components


def solve_edo3_step(
    n_current_kg_ha: float,
    p_current_kg_ha: float,
    k_current_kg_ha: float,
    w_mm: float,
    w_cc_mm: float,
    t_soil_c: float,
    crop: CropParameters,
    soil: Optional[SoilChemicalProperties] = None,
    erosion_rate_mm_day: float = 0.0,
    biomass_t_ha: Optional[float] = None,
    fertilizer_npk_kg_ha: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    is_crop: bool = True,
    dt_days: float = 1.0,
    # Calibration agrophysical parameters (defaults from GLOBAL_CONSTANTS)
    k_min0: Optional[float] = None,
    k_ln: Optional[float] = None,
    k_lk: Optional[float] = None,
    beta_k: Optional[float] = None,
    k_dec: Optional[float] = None,
    xi_n: Optional[float] = None,
    xi_p: Optional[float] = None,
    xi_k: Optional[float] = None,
    q10: Optional[float] = None
) -> EDO3StepOutput:
    """
    Integrates one time step dt of ODE 3 (Macronutrient Vector Dynamics).
    """
    if soil is None:
        soil = SoilChemicalProperties()

    # Load global constants
    q10_val = q10 if q10 is not None else float(GLOBAL_CONSTANTS.get("Q10", 2.0))
    k_min0_val = k_min0 if k_min0 is not None else float(GLOBAL_CONSTANTS.get("k_min0_dia", 0.0018))
    k_ln_val = k_ln if k_ln is not None else float(GLOBAL_CONSTANTS.get("k_lN", 0.035))
    k_lk_val = k_lk if k_lk is not None else float(GLOBAL_CONSTANTS.get("k_lK", 0.015))
    beta_k_val = beta_k if beta_k is not None else float(GLOBAL_CONSTANTS.get("beta_K", 0.65))
    k_dec_val = k_dec if k_dec is not None else float(GLOBAL_CONSTANTS.get("k_dec_dia", 0.025))
    xi_n_val = xi_n if xi_n is not None else float(GLOBAL_CONSTANTS.get("xi_N", 0.004))
    xi_p_val = xi_p if xi_p is not None else float(GLOBAL_CONSTANTS.get("xi_P", 0.008))
    xi_k_val = xi_k if xi_k is not None else float(GLOBAL_CONSTANTS.get("xi_K", 0.003))

    f_t = microbial_temperature_factor(t_soil_c, q10_val)
    phi_chem = calculate_phi_ph_ec(soil.ph, soil.ec_ds_m)

    # Relative root-zone moisture W / Wcc
    w_rel = max(0.0, min(1.2, w_mm / max(1.0, w_cc_mm)))
    eros = max(0.0, erosion_rate_mm_day)
    cic = max(1.0, soil.cic_cmolc_kg)

    # Active above-ground biomass
    b_act = biomass_t_ha if biomass_t_ha is not None else (crop.B_max_t_ha * 0.40 if is_crop else 2.0)

    # Physiological coefficients
    ic = 1.0 if is_crop else 0.0
    f_fix = crop.F_fix if is_crop else 0.0
    f_sol = crop.F_sol if is_crop else 0.0

    # Plant root uptake rates (calibrated for daily balance)
    ka_n = 0.008
    ka_p = 0.00010
    ka_k = 0.005

    # -------------------- 1. SOURCE VECTOR S(t) --------------------
    # Nitrogen: SN = FN_fert + Ffix,c * B + kmin0 * OM * (W/Wcc) * fT
    # Coefficients applied directly per PDF Section 3.2.3.
    organic_n_pool = soil.om_pct
    sn_mineralization = k_min0_val * organic_n_pool * w_rel * f_t
    sn_fixation = f_fix * b_act
    sn_total = fertilizer_npk_kg_ha[0] + sn_fixation + sn_mineralization

    # Phosphorus: SP = FP_fert + Fsol,c * B + basal mineralization
    sp_solubilization = f_sol * b_act
    sp_native = 0.0
    sp_total = fertilizer_npk_kg_ha[1] + sp_solubilization + sp_native

    # Potassium: SK = FK_fert + SK_res + basal clay release
    # SK_res = I(q = Transition) * beta_K * kdec * B
    sk_stover = (1.0 - ic) * beta_k_val * k_dec_val * b_act
    sk_native = 0.0
    sk_total = fertilizer_npk_kg_ha[2] + sk_stover + sk_native

    # ----------------- 2. LOSS RATE VECTOR Lambda(t) -----------------
    # Nitrogen: Lambda_N = (kl,N / CEC) * (W/Wcc) + Ic * phi_chem * ka_N * fT * (W/Wcc) + xi_N * eros
    lambda_n = w_rel * (k_ln_val / cic + ic * phi_chem * ka_n * f_t) + xi_n_val * eros

    # Phosphorus (immune to vertical leaching): Lambda_P = Ic * phi_chem * ka_P * fT * (W/Wcc) + xi_P * eros
    lambda_p = ic * phi_chem * ka_p * f_t * w_rel + xi_p_val * eros

    # Potassium: Lambda_K = (kl,K / CEC) * (W/Wcc) + Ic * phi_chem * ka_K * fT * (W/Wcc) + xi_K * eros
    lambda_k = w_rel * (k_lk_val / cic + ic * phi_chem * ka_k * f_t) + xi_k_val * eros

    # ----------------- 3. EXACT ANALYTICAL INTEGRATION -----------------
    # N(t + dt) = exp(-Lambda * dt) * N(t) + dt * phi1(Lambda * dt) * S
    zn = lambda_n * dt_days
    zp = lambda_p * dt_days
    zk = lambda_k * dt_days

    n_next = math.exp(-zn) * max(0.0, n_current_kg_ha) + dt_days * phi1(zn) * sn_total
    p_next = math.exp(-zp) * max(0.0, p_current_kg_ha) + dt_days * phi1(zp) * sp_total
    k_next = math.exp(-zk) * max(0.0, k_current_kg_ha) + dt_days * phi1(zk) * sk_total

    # Strict non-negative bound (AgroPhasor Biogeochemical Boundary)
    n_next = max(0.0, n_next)
    p_next = max(0.0, p_next)
    k_next = max(0.0, k_next)

    # Instantaneous derivatives dN/dt
    dn_dt = (n_next - n_current_kg_ha) / dt_days
    dp_dt = (p_next - p_current_kg_ha) / dt_days
    dk_dt = (k_next - k_current_kg_ha) / dt_days

    # Liebig's Law of the Minimum
    eta_val, limiting, components = compute_liebig_factor(
        n_next, p_next, k_next,
        kn=crop.K_N, kp=crop.K_P, kk=crop.K_K
    )

    # Step flux diagnostics
    leach_n = (k_ln_val / cic) * w_rel * 0.10 * n_current_kg_ha * dt_days
    leach_k = (k_lk_val / cic) * w_rel * 0.10 * k_current_kg_ha * dt_days
    eros_p = xi_p_val * eros * p_current_kg_ha * dt_days

    return EDO3StepOutput(
        n_kg_ha=round(n_next, 2),
        p_kg_ha=round(p_next, 2),
        k_kg_ha=round(k_next, 2),
        dn_dt=round(dn_dt, 3),
        dp_dt=round(dp_dt, 3),
        dk_dt=round(dk_dt, 3),
        eta_nutrientes=eta_val,
        limiting_nutrient=limiting,
        eta_components=components,
        biological_n_fixation_kg=round(sn_fixation * dt_days, 3),
        p_solubilization_kg=round(sp_solubilization * dt_days, 3),
        k_stover_recycling_kg=round(sk_stover * dt_days, 3),
        leaching_n_kg=round(leach_n, 3),
        leaching_k_kg=round(leach_k, 3),
        erosion_loss_p_kg=round(eros_p, 3),
        f_t_microbial=round(f_t, 3)
    )


def simulate_edo3_timeseries(
    w_series: List[float],
    t_soil_series: List[float],
    crop: CropParameters,
    soil: Optional[SoilChemicalProperties] = None,
    w_cc_mm: float = 120.0,
    n0_kg_ha: float = 85.0,
    p0_kg_ha: float = 32.0,
    k0_kg_ha: float = 180.0,
    erosion_rate_series: Optional[List[float]] = None,
    biomass_series: Optional[List[float]] = None,
    is_crop: bool = True,
    dt_days: float = 1.0
) -> Dict[str, Any]:
    """
    Runs a complete ODE 3 time-series simulation over a sequence of days.
    """
    n_steps = len(w_series)
    if len(t_soil_series) != n_steps:
        raise ValueError("w_series and t_soil_series must have the same length.")

    if soil is None:
        soil = SoilChemicalProperties()

    if erosion_rate_series is None:
        erosion_rate_series = [0.0] * n_steps

    curr_n = max(0.0, n0_kg_ha)
    curr_p = max(0.0, p0_kg_ha)
    curr_k = max(0.0, k0_kg_ha)

    hist_n = [curr_n]
    hist_p = [curr_p]
    hist_k = [curr_k]
    hist_eta = []
    hist_limiting = []
    hist_fix_n = []
    hist_sol_p = []
    hist_rec_k = []
    hist_leach_n = []
    hist_eros_p = []

    for step in range(n_steps):
        w_step = w_series[step]
        t_soil_step = t_soil_series[step]
        eros_step = erosion_rate_series[step]
        b_step = biomass_series[step] if biomass_series is not None else None

        out = solve_edo3_step(
            n_current_kg_ha=curr_n,
            p_current_kg_ha=curr_p,
            k_current_kg_ha=curr_k,
            w_mm=w_step,
            w_cc_mm=w_cc_mm,
            t_soil_c=t_soil_step,
            crop=crop,
            soil=soil,
            erosion_rate_mm_day=eros_step,
            biomass_t_ha=b_step,
            is_crop=is_crop,
            dt_days=dt_days
        )

        curr_n = out.n_kg_ha
        curr_p = out.p_kg_ha
        curr_k = out.k_kg_ha

        hist_n.append(curr_n)
        hist_p.append(curr_p)
        hist_k.append(curr_k)
        hist_eta.append(out.eta_nutrientes)
        hist_limiting.append(out.limiting_nutrient)
        hist_fix_n.append(out.biological_n_fixation_kg)
        hist_sol_p.append(out.p_solubilization_kg)
        hist_rec_k.append(out.k_stover_recycling_kg)
        hist_leach_n.append(out.leaching_n_kg)
        hist_eros_p.append(out.erosion_loss_p_kg)

    return {
        "crop": crop.name,
        "is_crop": is_crop,
        "n_series_kg_ha": hist_n,
        "p_series_kg_ha": hist_p,
        "k_series_kg_ha": hist_k,
        "eta_liebig_series": hist_eta,
        "limiting_nutrient_series": hist_limiting,
        "summary": {
            "initial_NPK": [n0_kg_ha, p0_kg_ha, k0_kg_ha],
            "final_NPK": [curr_n, curr_p, curr_k],
            "total_biological_n_fixed_kg_ha": round(sum(hist_fix_n), 2),
            "total_p_solubilized_kg_ha": round(sum(hist_sol_p), 2),
            "total_k_stover_recycled_kg_ha": round(sum(hist_rec_k), 2),
            "total_leached_n_kg_ha": round(sum(hist_leach_n), 2),
            "total_erosion_lost_p_kg_ha": round(sum(hist_eros_p), 2),
            "mean_eta_liebig": round(float(sum(hist_eta) / max(1, len(hist_eta))), 3),
            "final_eta_liebig": hist_eta[-1] if hist_eta else 0.0
        }
    }
