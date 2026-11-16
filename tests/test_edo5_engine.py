"""
Suite de Pruebas Unitarias para EDO 5: Erosión Hídrica de la Capa Fértil (AgroPhasor).
Verifica:
1. Validación estricta del catálogo JSON de parámetros para EDO 5 (gemini-code-1794737993920.json).
2. Criterio 1: Terreno plano (pendiente theta = 0°) produce erosión estrictamente nula (dH/dt = 0).
3. Criterio 2: Modulación topográfica SRTM monotónicamente creciente con sin(theta).
4. Criterio 3: Escudo mecánico exponencial de la biomasa foliar y rastrojo exp(-lambda_B * B).
5. Criterio 4: Conmutación de erodibilidad en transición/labranza (k_er,labranza vs k_er,cultivo, salto de 8.75x).
6. Criterio 5: Fronteras físicas de conservación, irreversibilidad (dH/dt <= 0) y no-negatividad (roca madre H >= 0).
7. Criterio 6: Acoplamiento edáfico con EDO 2 (reducción de Wcc) y arrastre mecánico de fósforo en EDO 3.
8. Criterio 7: Cálculo de la métrica de conservación de suelo del Frente de Pareto f2 y renderizado 3D.
9. Criterio 8: Simulación espacial 2.5D con detección de celdas críticas (hotspots de ladera).
"""

import math
import os
import unittest

from backend.models.edo5_validator import validate_edo5_catalog, EDO5ValidationError
from backend.core.edo5_engine import (
    solve_edo5_step,
    simulate_edo5_timeseries,
    compute_soil_pareto_metric_f2,
    compute_soil_color,
    EDO5StepOutput
)
from backend.services.parcel_edo5 import ParcelEDO5Service

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "gemini-code.json")


class TestEDO5Engine(unittest.TestCase):

    def test_json_catalog_validation_success(self):
        """Verifica que el archivo gemini-code.json sea 100% válido para EDO 5."""
        self.assertTrue(os.path.exists(JSON_PATH), f"No existe el archivo {JSON_PATH}")
        
        result = validate_edo5_catalog(JSON_PATH)
        self.assertTrue(result["valid"], f"Falló validación de JSON: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertGreaterEqual(result["crops_validated_count"], 2)
        
        # Verificar constantes globales para EDO 5
        global_p = result["global_parameters_edo5"]
        self.assertAlmostEqual(global_p["k_er_cultivo"], 0.0004)
        self.assertAlmostEqual(global_p["k_er_labranza"], 0.0035)
        self.assertAlmostEqual(global_p["lambda_B_ha_t"], 0.45)
        self.assertAlmostEqual(global_p["xi_N"], 0.004)
        self.assertAlmostEqual(global_p["xi_P"], 0.008)
        self.assertAlmostEqual(global_p["xi_K"], 0.003)
        
        # Verificar protección foliar de cultivos
        crops = result["crops_summary"]
        self.assertIn("Maiz_Zea_mays", crops)
        self.assertIn("Frijol_Phaseolus_vulgaris", crops)
        
        # Maíz: B_max = 22 t/ha -> protección foliar > 99.9%
        maiz = crops["Maiz_Zea_mays"]
        self.assertEqual(maiz["B_max_t_ha"], 22.0)
        self.assertGreater(maiz["soil_protection_peak_pct"], 99.9)
        
        # Frijol: B_max = 7.5 t/ha -> protección foliar > 96%
        frijol = crops["Frijol_Phaseolus_vulgaris"]
        self.assertEqual(frijol["B_max_t_ha"], 7.5)
        self.assertGreater(frijol["soil_protection_peak_pct"], 96.0)

    def test_json_catalog_validation_catches_invalid_parameters(self):
        """Verifica que el validador rechace catálogos con inconsistencias físicas."""
        # Caso 1: k_er_labranza <= k_er_cultivo (violación física)
        bad_catalog_1 = {
            "constantes_globales": {
                "k_er_cultivo": 0.005,
                "k_er_labranza": 0.001,  # Menor que cultivo: imposible
                "lambda_B_ha_t": 0.45,
                "xi_N": 0.004,
                "xi_P": 0.008,
                "xi_K": 0.003
            },
            "cultivos": {
                "Maiz": {"B_max_t_ha": 20.0, "B0_t_ha": 0.2, "duracion_dias": 120}
            }
        }
        res_1 = validate_edo5_catalog(bad_catalog_1)
        self.assertFalse(res_1["valid"])
        self.assertTrue(any("Inconsistencia física" in e for e in res_1["errors"]))

        # Caso 2: Parámetros negativos
        bad_catalog_2 = {
            "constantes_globales": {
                "k_er_cultivo": -0.0004,
                "k_er_labranza": 0.0035,
                "lambda_B_ha_t": 0.45,
                "xi_N": 0.004,
                "xi_P": 0.008,
                "xi_K": 0.003
            },
            "cultivos": {
                "Maiz": {"B_max_t_ha": 20.0, "B0_t_ha": 0.2, "duracion_dias": 120}
            }
        }
        res_2 = validate_edo5_catalog(bad_catalog_2)
        self.assertFalse(res_2["valid"])

    def test_criterion_1_flat_terrain_zero_erosion(self):
        """
        Criterio 1: En terreno horizontal (theta = 0°), sin(theta) = 0.
        La tasa de erosión debe ser matemáticamente cero sin importar la intensidad de lluvia
        o si el suelo está totalmente desprotegido.
        """
        h_initial = 400.0  # mm
        step = solve_edo5_step(
            h_current_mm=h_initial,
            precip_mm=95.0,        # Tormenta severa de 95 mm/día (GPM/IMERG)
            slope_deg=0.0,         # Terreno plano (SRTM)
            biomass_t_ha=0.0,      # Suelo totalmente desnudo
            is_transition=True,    # Ventana crítica de labranza
            h_initial_mm=h_initial
        )
        self.assertEqual(step.dh_dt_mm_day, 0.0)
        self.assertEqual(step.erosion_loss_step_mm, 0.0)
        self.assertEqual(step.h_current_mm, h_initial)
        self.assertEqual(step.topographic_factor_sin, 0.0)

    def test_criterion_2_slope_monotonicity_srtm(self):
        """
        Criterio 2: A mayor pendiente topográfica SRTM, la fuerza cortante del flujo
        aumenta estrictamente con sin(theta).
        theta_plano (0°) < theta_suave (3°) < theta_ladera (12°) < theta_escarpada (30°)
        """
        precip = 50.0  # mm/día
        biomass = 1.0  # t/ha
        slopes = [0.0, 3.0, 12.0, 30.0]
        losses = []

        for slope in slopes:
            step = solve_edo5_step(
                h_current_mm=400.0,
                precip_mm=precip,
                slope_deg=slope,
                biomass_t_ha=biomass,
                is_transition=False
            )
            losses.append(step.erosion_loss_step_mm)

        self.assertEqual(losses[0], 0.0)
        self.assertGreater(losses[1], losses[0])
        self.assertGreater(losses[2], losses[1])
        self.assertGreater(losses[3], losses[2])

    def test_criterion_3_canopy_biomass_exponential_shield(self):
        """
        Criterio 3: Atenuación exponencial del impacto de lluvia por biomasa foliar y rastrojos:
        factor_proteccion = exp(-lambda_B * B).
        Un cultivo denso (Maíz con B = 20 t/ha) reduce la erosión en más de 99.9% frente a suelo desnudo.
        """
        precip = 60.0
        slope = 15.0  # Ladera pronunciada
        lambda_b = 0.45

        # Caso A: Suelo desnudo (B = 0)
        step_bare = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=0.0, is_transition=False, lambda_b=lambda_b
        )
        self.assertAlmostEqual(step_bare.vegetation_cover_factor, 1.0)

        # Caso B: Cultivo incipiente (B = 2 t/ha)
        step_young = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=2.0, is_transition=False, lambda_b=lambda_b
        )
        self.assertAlmostEqual(step_young.vegetation_cover_factor, math.exp(-0.45 * 2.0), places=3)
        self.assertLess(step_young.erosion_loss_step_mm, step_bare.erosion_loss_step_mm)

        # Caso C: Cultivo cerrado de alta biomasa (B = 20 t/ha)
        step_dense = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=20.0, is_transition=False, lambda_b=lambda_b
        )
        expected_factor = math.exp(-0.45 * 20.0)  # ≈ 0.000123
        self.assertAlmostEqual(step_dense.vegetation_cover_factor, expected_factor, places=4)
        
        # Reducción > 99.9%
        efficiency = (1.0 - (step_dense.erosion_loss_step_mm / step_bare.erosion_loss_step_mm)) * 100.0
        self.assertGreater(efficiency, 99.9)

    def test_criterion_4_tillage_transition_jump(self):
        """
        Criterio 4: Salto discreto al conmutar a q(t) = Transición (labranza/suelo removido).
        k_er conmuta de k_er,cultivo (0.0004) a k_er,labranza (0.0035).
        La vulnerabilidad del suelo se multiplica exactamente por un factor de 8.75x.
        """
        precip = 40.0
        slope = 10.0
        biomass = 0.5  # Restos mínimos de rastrojo

        step_cultivo = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=biomass, is_transition=False,
            k_er_cultivo=0.0004, k_er_labranza=0.0035
        )
        step_labranza = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=biomass, is_transition=True,
            k_er_cultivo=0.0004, k_er_labranza=0.0035
        )

        ratio = step_labranza.erosion_loss_step_mm / step_cultivo.erosion_loss_step_mm
        self.assertAlmostEqual(ratio, 0.0035 / 0.0004, places=2)  # Exactamente 8.75
        self.assertEqual(step_labranza.erodibility_k_er, 0.0035)
        self.assertEqual(step_cultivo.erodibility_k_er, 0.0004)

    def test_criterion_5_non_negativity_and_irreversibility(self):
        """
        Criterio 5: Fronteras físicas:
        - Irreversibilidad: dH/dt <= 0 siempre.
        - No-negatividad estricta: H no puede ser menor a 0 (corte en roca madre).
        """
        h_initial = 10.0  # Suelo superficial degradado
        # Simular una tormenta masiva cataclísmica
        step_over = solve_edo5_step(
            h_current_mm=2.0,
            precip_mm=1000.0,
            slope_deg=45.0,
            biomass_t_ha=0.0,
            is_transition=True,
            h_initial_mm=h_initial
        )
        # H debe quedar acotado exactamente en 0
        self.assertEqual(step_over.h_current_mm, 0.0)
        self.assertEqual(step_over.soil_retention_ratio, 0.0)
        self.assertTrue(step_over.is_bedrock_exposed)
        self.assertLessEqual(step_over.dh_dt_mm_day, 0.0)

        # Si ya se encuentra en 0, no puede haber más erosión
        step_zero = solve_edo5_step(
            h_current_mm=0.0,
            precip_mm=50.0,
            slope_deg=20.0,
            biomass_t_ha=0.0,
            is_transition=True,
            h_initial_mm=h_initial
        )
        self.assertEqual(step_zero.h_current_mm, 0.0)
        self.assertEqual(step_zero.erosion_loss_step_mm, 0.0)
        self.assertEqual(step_zero.dh_dt_mm_day, 0.0)

    def test_criterion_6_edaphic_and_biochemical_coupling(self):
        """
        Criterio 6: Acoplamiento físico con los otros subsistemas:
        - Al reducirse H, la capacidad de retención hídrica de EDO 2 colapsa: Wcc(H) = theta_fc * H.
        - Arrastre mecánico de macronutrientes en EDO 3: xi * Delta_H * Nutriente (especialmente Fósforo).
        """
        theta_fc = 0.32
        theta_wp = 0.15
        h0 = 400.0  # Wcc_0 = 128.0 mm
        
        nutrients = {"N": 120.0, "P": 45.0, "K": 150.0}
        
        step = solve_edo5_step(
            h_current_mm=300.0,
            precip_mm=80.0,
            slope_deg=18.0,
            biomass_t_ha=0.2,
            is_transition=True,
            h_initial_mm=h0,
            theta_fc=theta_fc,
            theta_wp=theta_wp,
            current_nutrients_kg_ha=nutrients,
            xi_p=0.008
        )
        
        self.assertLess(step.h_current_mm, 300.0)
        # Wcc debe reducirse en sincronía
        # Conservar precisión física; el redondeo corresponde a presentación.
        expected_w_cc = theta_fc * step.h_current_mm
        self.assertAlmostEqual(step.w_cc_mm, expected_w_cc)
        
        # Debe haber pérdida de fósforo por arrastre
        p_loss = step.nutrient_drag_kg_ha["P"]
        self.assertGreater(p_loss, 0.0)
        # Integral de P'=-xi*Hloss*P, no flujo Euler con P inicial.
        expected_p_loss = -math.expm1(-0.008 * step.erosion_loss_step_mm) * nutrients["P"]
        self.assertAlmostEqual(p_loss, expected_p_loss)

    def test_criterion_7_pareto_metric_f2_and_visual_subsidence(self):
        """
        Criterio 7: Evaluación de la función de coste f2 (Mejor Tierra al Final)
        y visualización 3D (hundimiento de vértices y color de suelo marrón a gris).
        """
        # Comparación de dos rotaciones:
        # Rotación A (Conservacionista): H final = 390 mm sobre 400 mm (pérdida 2.5%), fertilidad eta_N = 0.85
        f2_cons = compute_soil_pareto_metric_f2(
            h_initial=400.0, h_final=390.0, chemical_health_eta_n=0.85, omega_h=0.5, omega_n=0.5
        )
        
        # Rotación B (Erosiva con laboreo intenso en lluvias): H final = 300 mm (pérdida 25%), eta_N = 0.40
        f2_eros = compute_soil_pareto_metric_f2(
            h_initial=400.0, h_final=300.0, chemical_health_eta_n=0.40, omega_h=0.5, omega_n=0.5
        )
        
        # En la formulación de Pareto (minimización de degradación), f2_cons < f2_eros
        self.assertLess(f2_cons, f2_eros)
        self.assertAlmostEqual(f2_cons, 0.5 * (10.0 / 400.0) + 0.5 * (1.0 - 0.85), places=3)
        self.assertAlmostEqual(f2_eros, 0.5 * (100.0 / 400.0) + 0.5 * (1.0 - 0.40), places=3)

        # Verificación cromática: marrón para suelo sano, gris para degradado
        color_intact = compute_soil_color(retention_ratio=1.0)
        color_ruined = compute_soil_color(retention_ratio=0.0)
        self.assertEqual(color_intact, (101, 67, 33))   # Marrón fértil
        self.assertEqual(color_ruined, (128, 128, 128)) # Gris rocoso

    def test_criterion_8_parcel_edo5_spatial_service(self):
        """
        Criterio 8: Simulación 2.5D espacial multi-celda.
        Verifica que la celda con mayor pendiente en la ladera sea identificada como el hotspot crítico de erosión.
        """
        grid = [
            {"cell_id": "c_plano", "altitude_m": 3100.0, "slope_deg": 1.0},
            {"cell_id": "c_ladera_media", "altitude_m": 3150.0, "slope_deg": 8.0},
            {"cell_id": "c_ladera_pronunciada", "altitude_m": 3220.0, "slope_deg": 22.0}
        ]
        
        days = 30
        precip = [30.0 if d % 2 == 0 else 5.0 for d in range(days)]
        biomass = [0.5 for _ in range(days)]
        flags = [False for _ in range(days)]

        res = ParcelEDO5Service.simulate_parcel_grid(
            grid_cells=grid,
            precip_series=precip,
            biomass_series=biomass,
            transition_flags=flags,
            default_h0_mm=400.0
        )

        self.assertEqual(res["cells_count"], 3)
        self.assertEqual(res["hotspot_critical_cell"], "c_ladera_pronunciada")
        self.assertGreater(res["hotspot_max_loss_mm"], 0.0)
        
        # Verificar orden de pérdidas por pendiente
        cell_dict = {c["cell_id"]: c["erosion_loss_mm"] for c in res["cells"]}
        self.assertLess(cell_dict["c_plano"], cell_dict["c_ladera_media"])
        self.assertLess(cell_dict["c_ladera_media"], cell_dict["c_ladera_pronunciada"])


if __name__ == "__main__":
    unittest.main()
