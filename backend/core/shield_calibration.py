"""
Calibración Supervisada y Validación Cruzada del Escudo Ambiental (Lissajous + EDO 1-3)
frente a biomas y escenarios agronómicos etiquetados (Selva, Desiertos, Campos Andinos,
Campos Templados, Estrés Moderado y Heladas).

Permite variar y ajustar los parámetros del escudo (`A_L_ref_C2`, `peso_lissajous_escudo_omega_L`,
`escudo_psi_ref`, `escudo_psi_exp`) mediante búsqueda multi-escala + descenso coordinado
sobre un conjunto de entrenamiento y validar su precisión fuera de muestra (K-Fold estratificado).
"""

from dataclasses import dataclass
import math
from typing import Dict, Any, List, Optional, Tuple

from backend.models.crop_parameters import get_crop_parameters, GLOBAL_CONSTANTS
from backend.core.edo1_engine import simulate_canopy_diurnal_cycle
from backend.core.edo2_engine import compute_soil_limits, relative_stomatal_conductance
from backend.core.edo3_engine import solve_edo3_step, SoilChemicalProperties
from backend.core.physics import thermal_comfort_index


@dataclass(frozen=True)
class LabeledBiomeScenario:
    scenario_id: str
    biome: str          # "Selva" | "Desierto" | "Campo_Andino" | "Campo_Templado" | "Helada"
    crop_id: str
    t_mean_c: float
    t_amp_c: float
    rad_peak_wm2: float
    rh_mean_pct: float
    water_fraction: float   # Fracción de agua útil entre W_pmp y W_cc [0, 1]
    npk: Tuple[float, float, float]
    expected_state: str     # "azul_cobalto" | "violeta_ambar" | "rojo_intenso"
    target_score: float     # Puntaje continuo de referencia en [0, 1]


# Conjunto de referencia etiquetado por biomas y cultivos reales (24 escenarios)
LABELED_BIOME_SCENARIOS: Tuple[LabeledBiomeScenario, ...] = (
    # --- SELVA HÚMEDA / TROPICAL ---
    LabeledBiomeScenario("selva_maiz_opt", "Selva", "maiz", 26.5, 4.5, 680.0, 82.0, 0.85, (110.0, 45.0, 180.0), "azul_cobalto", 0.86),
    LabeledBiomeScenario("selva_maiz_lluvia", "Selva", "maiz", 25.5, 4.0, 620.0, 86.0, 0.92, (95.0, 38.0, 165.0), "azul_cobalto", 0.84),
    LabeledBiomeScenario("selva_frijol_opt", "Selva", "frijol", 24.5, 4.0, 600.0, 80.0, 0.82, (100.0, 40.0, 160.0), "azul_cobalto", 0.82),
    LabeledBiomeScenario("selva_fresa_calor_mod", "Selva", "fresa", 25.0, 4.5, 640.0, 78.0, 0.78, (90.0, 36.0, 150.0), "violeta_ambar", 0.56),
    LabeledBiomeScenario("selva_papa_estres_termico", "Selva", "papa", 27.5, 4.5, 690.0, 82.0, 0.85, (85.0, 32.0, 180.0), "rojo_intenso", 0.22),
    LabeledBiomeScenario("selva_papa_extrema", "Selva", "papa", 29.5, 5.0, 740.0, 84.0, 0.80, (85.0, 32.0, 180.0), "rojo_intenso", 0.12),

    # --- CAMPOS ANDINOS (SIERRA) ---
    LabeledBiomeScenario("andino_papa_opt", "Campo_Andino", "papa", 15.0, 6.0, 720.0, 65.0, 0.80, (105.0, 45.0, 170.0), "azul_cobalto", 0.84),
    LabeledBiomeScenario("andino_papa_fresco", "Campo_Andino", "papa", 13.5, 5.5, 680.0, 68.0, 0.75, (95.0, 40.0, 160.0), "azul_cobalto", 0.80),
    LabeledBiomeScenario("andino_fresa_opt", "Campo_Andino", "fresa", 17.0, 6.0, 700.0, 65.0, 0.82, (100.0, 42.0, 165.0), "azul_cobalto", 0.85),
    LabeledBiomeScenario("andino_maiz_frio_mod", "Campo_Andino", "maiz", 14.5, 6.0, 680.0, 62.0, 0.75, (95.0, 38.0, 155.0), "violeta_ambar", 0.54),
    LabeledBiomeScenario("andino_frijol_frio_mod", "Campo_Andino", "frijol", 14.0, 5.5, 650.0, 65.0, 0.72, (90.0, 35.0, 150.0), "violeta_ambar", 0.52),

    # --- CAMPOS TEMPLADOS / COSTA IRRIGADA ---
    LabeledBiomeScenario("templado_maiz_opt", "Campo_Templado", "maiz", 22.0, 5.5, 700.0, 64.0, 0.78, (105.0, 42.0, 160.0), "azul_cobalto", 0.85),
    LabeledBiomeScenario("templado_frijol_opt", "Campo_Templado", "frijol", 21.0, 5.0, 660.0, 65.0, 0.80, (95.0, 40.0, 155.0), "azul_cobalto", 0.85),
    LabeledBiomeScenario("templado_fresa_opt", "Campo_Templado", "fresa", 19.5, 5.0, 640.0, 68.0, 0.85, (100.0, 42.0, 160.0), "azul_cobalto", 0.88),
    LabeledBiomeScenario("templado_maiz_deficit_agua", "Campo_Templado", "maiz", 24.0, 7.0, 780.0, 48.0, 0.35, (75.0, 30.0, 120.0), "violeta_ambar", 0.50),
    LabeledBiomeScenario("templado_frijol_deficit_npk", "Campo_Templado", "frijol", 21.5, 5.0, 650.0, 62.0, 0.75, (18.0, 8.0, 35.0), "violeta_ambar", 0.45),

    # --- DESIERTOS Y SEQUÍAS EXTREMAS ---
    LabeledBiomeScenario("desierto_maiz_sequia", "Desierto", "maiz", 33.0, 10.0, 950.0, 18.0, 0.05, (20.0, 10.0, 40.0), "rojo_intenso", 0.08),
    LabeledBiomeScenario("desierto_papa_sequia", "Desierto", "papa", 31.5, 10.0, 920.0, 20.0, 0.05, (25.0, 12.0, 45.0), "rojo_intenso", 0.06),
    LabeledBiomeScenario("desierto_frijol_sequia", "Desierto", "frijol", 32.5, 9.5, 900.0, 22.0, 0.08, (22.0, 10.0, 38.0), "rojo_intenso", 0.09),
    LabeledBiomeScenario("desierto_fresa_sequia", "Desierto", "fresa", 30.5, 9.0, 880.0, 22.0, 0.04, (20.0, 9.0, 35.0), "rojo_intenso", 0.07),

    # --- HELADAS ALTOANDINAS ---
    LabeledBiomeScenario("helada_frijol_critico", "Helada", "frijol", 3.0, 4.0, 350.0, 75.0, 0.65, (80.0, 30.0, 140.0), "rojo_intenso", 0.05),
    LabeledBiomeScenario("helada_maiz_critico", "Helada", "maiz", 1.5, 4.0, 320.0, 78.0, 0.65, (80.0, 30.0, 140.0), "rojo_intenso", 0.05),
    LabeledBiomeScenario("helada_papa_severa", "Helada", "papa", -1.5, 3.5, 280.0, 80.0, 0.65, (80.0, 30.0, 140.0), "rojo_intenso", 0.04),
    LabeledBiomeScenario("helada_fresa_severa", "Helada", "fresa", -2.5, 3.5, 260.0, 82.0, 0.65, (80.0, 30.0, 140.0), "rojo_intenso", 0.04),
)


@dataclass(frozen=True)
class EvaluatedScenarioFeatures:
    scenario: LabeledBiomeScenario
    lissajous_area_eff: float
    psi_environmental: float
    mean_tc: float
    eta_w: float
    eta_n: float


def evaluate_biome_features(
    scenarios: Tuple[LabeledBiomeScenario, ...] = LABELED_BIOME_SCENARIOS,
) -> List[EvaluatedScenarioFeatures]:
    """Ejecuta los motores físicos reales EDO 1-3 sobre cada escenario etiquetado."""
    features: List[EvaluatedScenarioFeatures] = []
    for sc in scenarios:
        crop = get_crop_parameters(sc.crop_id)
        limits = compute_soil_limits(crop, 0.30, 0.14, 400.0)
        water = limits.w_pmp + sc.water_fraction * (limits.w_cc - limits.w_pmp)
        t_air = [sc.t_mean_c + sc.t_amp_c * math.sin((h - 9) * math.pi / 12.0) for h in range(24)]
        f_rad = [max(0.0, sc.rad_peak_wm2 * math.sin((h - 6) * math.pi / 12.0)) for h in range(24)]
        rh = [max(10.0, min(95.0, sc.rh_mean_pct - 12.0 * math.sin((h - 9) * math.pi / 12.0))) for h in range(24)]

        diurnal = simulate_canopy_diurnal_cycle(t_air, f_rad, rh, water, crop)
        eta_w = relative_stomatal_conductance(water, limits)
        edo3 = solve_edo3_step(
            *sc.npk,
            w_mm=water,
            w_cc_mm=limits.w_cc,
            t_soil_c=sc.t_mean_c,
            crop=crop,
            soil=SoilChemicalProperties(),
            is_crop=True,
        )
        tc_series = [thermal_comfort_index(t, crop.T_opt, crop.delta_T_tol) for t in diurnal["t_canopy_hourly"]]
        mean_tc = sum(tc_series) / max(1, len(tc_series))
        psi_env = mean_tc * eta_w * edo3.eta_nutrientes
        al_eff = diurnal["lissajous_area"] * eta_w * mean_tc

        features.append(
            EvaluatedScenarioFeatures(
                scenario=sc,
                lissajous_area_eff=al_eff,
                psi_environmental=psi_env,
                mean_tc=mean_tc,
                eta_w=eta_w,
                eta_n=edo3.eta_nutrientes,
            )
        )
    return features


def predict_shield_score_parametric(
    lissajous_area_eff: float,
    psi_environmental: float,
    a_l_ref: float,
    omega_l: float,
    psi_ref: float,
    psi_exp: float,
) -> float:
    """
    Función de respuesta paramétrica del Escudo Ambiental y Lissajous:
        f_psi = (psi / (psi + psi_ref)) ** psi_exp
        f_L   = A_L_eff / (A_L_eff + a_l_ref)
        score = f_psi * ((1 - omega_l) + omega_l * f_L)

    Propiedades físicas garantizadas:
    - Si el cultivo es inviable (psi -> 0 en desierto/helada), score -> 0 (Rojo Intenso).
    - A igualdad de condiciones fisiológicas, mayor área efectiva de Lissajous aumenta el escudo.
    """
    al = max(0.0, float(lissajous_area_eff))
    psi = max(0.0, min(1.0, float(psi_environmental)))
    if psi <= 0.0:
        return 0.0
    p_ref = max(1e-4, float(psi_ref))
    p_exp = max(0.1, float(psi_exp))
    l_ref = max(1e-4, float(a_l_ref))
    w_l = max(0.0, min(1.0, float(omega_l)))

    f_psi = math.pow(psi, p_exp) / (math.pow(psi, p_exp) + math.pow(p_ref, p_exp))
    f_l = al / (al + l_ref)
    score = f_psi * ((1.0 - w_l) + w_l * f_l)
    return max(0.0, min(1.0, score))


def classify_shield_state(score: float) -> str:
    if score >= 0.70:
        return "azul_cobalto"
    if score >= 0.38:
        return "violeta_ambar"
    return "rojo_intenso"


def _loss_on_features(
    params: Tuple[float, float, float, float],
    features: List[EvaluatedScenarioFeatures],
) -> Tuple[float, float]:
    """Calcula (loss_combinada, accuracy) sobre una lista de características evaluadas."""
    a_l_ref, omega_l, psi_ref, psi_exp = params
    sq_err = 0.0
    correct = 0
    misclass_penalty = 0.0
    for f in features:
        pred = predict_shield_score_parametric(
            f.lissajous_area_eff, f.psi_environmental, a_l_ref, omega_l, psi_ref, psi_exp
        )
        sq_err += (pred - f.scenario.target_score) ** 2
        pred_cls = classify_shield_state(pred)
        if pred_cls == f.scenario.expected_state:
            correct += 1
        else:
            # Penalización cuadrática extra si cae fuera del umbral de su clase esperada
            if f.scenario.expected_state == "azul_cobalto":
                misclass_penalty += (0.72 - pred) ** 2 + 0.05
            elif f.scenario.expected_state == "rojo_intenso":
                misclass_penalty += (pred - 0.36) ** 2 + 0.05
            else:
                dist = max(0.0, 0.38 - pred, pred - 0.70)
                misclass_penalty += dist ** 2 + 0.05
    n = max(1, len(features))
    return (sq_err / n) + 1.5 * (misclass_penalty / n), correct / n


def fit_shield_parameters(
    train_features: List[EvaluatedScenarioFeatures],
) -> Dict[str, Any]:
    """
    Optimiza `(a_l_ref, omega_l, psi_ref, psi_exp)` mediante búsqueda en grilla gruesa
    seguida de refinamiento por descenso coordinado sobre `train_features`.
    """
    bounds = [
        (0.5, 10.0),   # a_l_ref
        (0.10, 0.70),  # omega_l
        (0.15, 0.55),  # psi_ref (punto medio Hill)
        (0.80, 3.50),  # psi_exp (pendiente Hill)
    ]

    best_params = (2.0, 0.25, 0.30, 1.8)
    best_loss, best_acc = _loss_on_features(best_params, train_features)

    # 1. Búsqueda gruesa en grilla multi-dimensional
    for l_ref in (0.8, 1.5, 2.5, 4.0, 6.0):
        for w_l in (0.15, 0.25, 0.35, 0.50):
            for p_ref in (0.20, 0.28, 0.35, 0.42):
                for p_exp in (1.2, 1.8, 2.4, 3.0):
                    cand = (l_ref, w_l, p_ref, p_exp)
                    loss, acc = _loss_on_features(cand, train_features)
                    if loss < best_loss:
                        best_loss, best_acc, best_params = loss, acc, cand

    # 2. Refinamiento local por descenso coordinado (Pattern Search)
    curr = list(best_params)
    steps = [0.4, 0.04, 0.02, 0.1]
    for _ in range(5):
        improved = False
        for dim in range(4):
            for direction in (-1.0, 1.0):
                cand = list(curr)
                cand[dim] = max(bounds[dim][0], min(bounds[dim][1], cand[dim] + direction * steps[dim]))
                cand_t = tuple(cand)
                loss, acc = _loss_on_features(cand_t, train_features)
                if loss < best_loss - 1e-9:
                    best_loss, best_acc, curr = loss, acc, cand
                    improved = True
        if not improved:
            steps = [s * 0.5 for s in steps]

    return {
        "a_l_ref": round(curr[0], 4),
        "omega_l": round(curr[1], 4),
        "psi_ref": round(curr[2], 4),
        "psi_exp": round(curr[3], 4),
        "train_loss": round(best_loss, 6),
        "train_accuracy": round(best_acc, 4),
    }


def run_stratified_cross_validation(
    k_folds: int = 4,
    scenarios: Tuple[LabeledBiomeScenario, ...] = LABELED_BIOME_SCENARIOS,
) -> Dict[str, Any]:
    """
    Ejecuta validación cruzada estratificada (K-Fold) por clase (`azul_cobalto`,
    `violeta_ambar`, `rojo_intenso`) para verificar que los parámetros calibrados
    generalicen fuera de muestra a biomas/cultivos no vistos en el ajuste.
    """
    all_features = evaluate_biome_features(scenarios)

    # Agrupar estratificadamente por clase esperada
    by_class: Dict[str, List[EvaluatedScenarioFeatures]] = {
        "azul_cobalto": [],
        "violeta_ambar": [],
        "rojo_intenso": [],
    }
    for feat in all_features:
        by_class[feat.scenario.expected_state].append(feat)

    folds: List[List[EvaluatedScenarioFeatures]] = [[] for _ in range(k_folds)]
    for cls_items in by_class.values():
        for idx, item in enumerate(cls_items):
            folds[idx % k_folds].append(item)

    fold_reports: List[Dict[str, Any]] = []
    oos_predictions: List[Dict[str, Any]] = []
    oos_correct = 0
    oos_sq_err = 0.0

    for fold_idx in range(k_folds):
        val_set = folds[fold_idx]
        train_set = [x for j, f in enumerate(folds) if j != fold_idx for x in f]
        fitted = fit_shield_parameters(train_set)
        params = (fitted["a_l_ref"], fitted["omega_l"], fitted["psi_ref"], fitted["psi_exp"])

        fold_correct = 0
        for item in val_set:
            pred = predict_shield_score_parametric(item.lissajous_area_eff, item.psi_environmental, *params)
            pred_cls = classify_shield_state(pred)
            is_ok = pred_cls == item.scenario.expected_state
            if is_ok:
                fold_correct += 1
                oos_correct += 1
            oos_sq_err += (pred - item.scenario.target_score) ** 2
            oos_predictions.append({
                "scenario_id": item.scenario.scenario_id,
                "biome": item.scenario.biome,
                "crop": item.scenario.crop_id,
                "expected": item.scenario.expected_state,
                "predicted": pred_cls,
                "score": round(pred, 4),
                "target": item.scenario.target_score,
                "correct": is_ok,
                "fold": fold_idx + 1,
            })

        fold_reports.append({
            "fold": fold_idx + 1,
            "val_size": len(val_set),
            "val_accuracy": round(fold_correct / max(1, len(val_set)), 4),
            "fitted_params": fitted,
        })

    # Ajuste final sobre el 100% de los datos etiquetados
    final_fit = fit_shield_parameters(all_features)
    n_total = max(1, len(all_features))

    return {
        "total_scenarios": len(all_features),
        "k_folds": k_folds,
        "oos_accuracy": round(oos_correct / n_total, 4),
        "oos_rmse": round(math.sqrt(oos_sq_err / n_total), 4),
        "final_parameters": final_fit,
        "fold_reports": fold_reports,
        "oos_predictions": oos_predictions,
    }


if __name__ == "__main__":
    report = run_stratified_cross_validation(k_folds=4)
    print("=== CALIBRACIÓN SUPERVISADA Y VALIDACIÓN CRUZADA DEL ESCUDO ===")
    print(f"Escenarios evaluados: {report['total_scenarios']} (K={report['k_folds']} folds estratificados)")
    print(f"Precisión fuera de muestra (OOS Accuracy): {report['oos_accuracy']*100:.1f}%")
    print(f"RMSE fuera de muestra (OOS RMSE): {report['oos_rmse']:.4f}")
    print("Parámetros óptimos calibrados:", report["final_parameters"])
    print("\nDetalle de predicciones fuera de muestra por bioma:")
    for row in report["oos_predictions"]:
        mark = "OK" if row["correct"] else "ERR"
        print(
            f"  [{mark:3s}] {row['scenario_id']:28s} ({row['biome']:14s}) | "
            f"esperado={row['expected']:13s} | predicho={row['predicted']:13s} | score={row['score']:.3f}"
        )
