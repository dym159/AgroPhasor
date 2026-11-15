"""
Suite de Pruebas Unitarias para EDO 2: Balance Hidrológico Radicular (AgroPhasor).
Verifica:
1. Validación estricta del catálogo JSON de parámetros para EDO 2.
2. Fronteras físicas de conservación de masa y corte de escorrentía (0 <= W <= Wcc).
3. Respuesta de conductancia estomática y transiciones de confort, estrés y marchitez.
4. Efecto de modulación topográfica SRTM (pendiente 0° vs ladera).
5. Activación de alertas de riego y cálculo exacto de la lámina de reposición.
6. Respuesta hídrica diferenciada entre Maíz y Frijol calibrados desde el JSON.
"""

import math
import os
import unittest

from backend.models.edo2_validator import validate_edo2_catalog, EDO2ValidationError
from backend.models.crop_parameters import get_crop_parameters, CropParameters
from backend.core.edo2_engine import (
    solve_edo2_step,
    simulate_edo2_timeseries,
    compute_soil_limits,
    SoilHydraulicLimits
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "gemini-code-1794737993920.json")


class TestEDO2Engine(unittest.TestCase):

    def test_json_catalog_validation_success(self):
        """Verifica que el archivo gemini-code-1794737993920.json sea 100% válido para EDO 2."""
        self.assertTrue(os.path.exists(JSON_PATH), f"No existe el archivo {JSON_PATH}")
        
        result = validate_edo2_catalog(JSON_PATH)
        self.assertTrue(result["valid"], f"Falló validación de JSON: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertGreaterEqual(result["crops_validated_count"], 2)
        
        # Verificar constantes globales para EDO 2
        global_p = result["global_parameters_edo2"]
        self.assertAlmostEqual(global_p["E_suelo0_mm_dia"], 4.2)
        self.assertAlmostEqual(global_p["lambda_B_ha_t"], 0.45)
        
        # Verificar límites de Maíz
        crops = result["crops_summary"]
        self.assertIn("Maiz_Zea_mays", crops)
        maiz = crops["Maiz_Zea_mays"]
        self.assertEqual(maiz["Zr_mm"], 1000.0)
        self.assertEqual(maiz["p_agotamiento"], 0.55)
        self.assertEqual(maiz["W_cc_mm"], 300.0)    # 0.30 * 1000
        self.assertEqual(maiz["W_pmp_mm"], 140.0)   # 0.14 * 1000
        self.assertEqual(maiz["W_crit_mm"], 212.0)  # 300 - 0.55*(300 - 140)
        self.assertEqual(maiz["RAW_mm"], 88.0)
        
        # Verificar límites de Frijol
        self.assertIn("Frijol_Phaseolus_vulgaris", crops)
        frijol = crops["Frijol_Phaseolus_vulgaris"]
        self.assertEqual(frijol["Zr_mm"], 600.0)
        self.assertEqual(frijol["p_agotamiento"], 0.45)
        self.assertEqual(frijol["W_cc_mm"], 180.0)   # 0.30 * 600
        self.assertEqual(frijol["W_pmp_mm"], 84.0)   # 0.14 * 600
        self.assertEqual(frijol["W_crit_mm"], 136.8) # 180 - 0.45*(180 - 84)
        self.assertEqual(frijol["RAW_mm"], 43.2)

    def test_json_catalog_validation_catches_invalid_parameters(self):
        """Verifica que el validador rechace catálogos con errores físicos en EDO 2."""
        invalid_catalog = {
            "constantes_globales": {
                "E_suelo0_mm_dia": -5.0,  # Inválido: negativo
                "lambda_B_ha_t": 0.0      # Inválido: <= 0
            },
            "suelo_desnudo_transicion": {
                "gamma_max": 0.05         # Inválido: debe ser 0 en suelo desnudo
            },
            "cultivos": {
                "Cultivo_Invalido": {
                    "Zr_mm": -100.0,       # Inválido: negativo
                    "p_agotamiento": 1.5,  # Inválido: > 1
                    "gamma_max": 0.0       # Inválido: <= 0 para cultivo vivo
                }
            }
        }
        res = validate_edo2_catalog(invalid_catalog)
        self.assertFalse(res["valid"])
        self.assertTrue(any("E_suelo0_mm_dia" in err for err in res["errors"]))
        self.assertTrue(any("lambda_B_ha_t" in err for err in res["errors"]))
        self.assertTrue(any("suelo_desnudo_transicion" in err for err in res["errors"]))
        self.assertTrue(any("Zr_mm" in err for err in res["errors"]))
        self.assertTrue(any("p_agotamiento" in err for err in res["errors"]))

    def test_physical_boundaries_and_runoff_generation(self):
        """
        Criterio 1: Acotamiento estricto 0 <= W <= Wcc.
        Si la precipitación supera la capacidad de campo, el excedente debe ser
        descartado exactamente como escorrentía superficial sin saturar numéricamente el suelo.
        """
        crop = get_crop_parameters("maiz")
        limits = compute_soil_limits(crop, theta_fc=0.30, theta_wp=0.14)
        w_cc = limits.w_cc  # e.g., 300 mm
        
        # Caso 1: Suelo ya en Wcc que recibe una lluvia torrencial de 150 mm
        step = solve_edo2_step(
            w_current_mm=w_cc,
            precip_mm=150.0,
            t_air_c=18.0,
            rh_pct=95.0,
            slope_deg=0.0,
            crop=crop,
            theta_fc=0.30,
            theta_wp=0.14
        )
        self.assertEqual(step.soil_water_mm, w_cc)
        self.assertGreater(step.runoff_mm, 140.0)
        self.assertAlmostEqual(step.soil_water_mm + step.runoff_mm, w_cc + step.infiltration_mm - step.etc_mm, places=2)

        # Caso 2: Suelo seco sometido a drenaje no puede ser negativo
        step_dry = solve_edo2_step(
            w_current_mm=0.5,
            precip_mm=0.0,
            t_air_c=35.0,
            rh_pct=10.0,
            slope_deg=30.0,
            crop=crop
        )
        self.assertGreaterEqual(step_dry.soil_water_mm, 0.0)

    def test_stomatal_conductance_transitions(self):
        """
        Criterio 2: Dinámica de regulación estomática gamma_c(W):
        - W >= W_crit: Confort hídrico (gamma_rel = 1.0).
        - W_pmp < W < W_crit: Estrés con decaimiento lineal de apertura.
        - W <= W_pmp: Marchitez permanente (gamma_rel = 0.0, Escudo Rojo).
        """
        crop = get_crop_parameters("maiz")
        limits = compute_soil_limits(crop, theta_fc=0.30, theta_wp=0.14)
        w_cc = limits.w_cc
        w_crit = limits.w_crit
        w_pmp = limits.w_pmp

        # Zona 1: Confort óptimo (W en capacidad de campo Wcc = 300 mm > Wcrit = 212 mm)
        step_opt = solve_edo2_step(
            w_current_mm=w_cc,
            precip_mm=0.0,
            t_air_c=22.0,
            rh_pct=60.0,
            slope_deg=0.0,
            crop=crop,
            theta_fc=0.30,
            theta_wp=0.14
        )
        self.assertEqual(step_opt.gamma_c_relative, 1.0)
        self.assertGreater(step_opt.soil_water_mm, w_crit)
        self.assertFalse(step_opt.is_irrigation_needed)
        self.assertFalse(step_opt.is_wilting)

        # Zona 2: Estrés medio (punto medio entre Wpmp y Wcrit)
        w_mid = (w_crit + w_pmp) / 2.0
        step_stress = solve_edo2_step(
            w_current_mm=w_mid,
            precip_mm=0.0,
            t_air_c=22.0,
            rh_pct=60.0,
            slope_deg=0.0,
            crop=crop,
            theta_fc=0.30,
            theta_wp=0.14
        )
        self.assertAlmostEqual(step_stress.gamma_c_relative, 0.5, places=2)
        self.assertTrue(step_stress.is_irrigation_needed)
        self.assertFalse(step_stress.is_wilting)

        # Zona 3: Marchitez permanente (W <= Wpmp)
        step_wilt = solve_edo2_step(
            w_current_mm=w_pmp - 5.0,
            precip_mm=0.0,
            t_air_c=22.0,
            rh_pct=60.0,
            slope_deg=0.0,
            crop=crop,
            theta_fc=0.30,
            theta_wp=0.14
        )
        self.assertEqual(step_wilt.gamma_c_relative, 0.0)
        self.assertEqual(step_wilt.transpiration_mm, 0.0)
        self.assertTrue(step_wilt.is_wilting)

    def test_bare_soil_transition_regime(self):
        """
        Verifica el régimen de q(t) = Transición (barbecho / rastrojo):
        La transpiración vegetal se anula completamente y solo actúa la evaporación
        del suelo protegida por el rastrojo remanente.
        """
        crop = get_crop_parameters("maiz")
        step_trans = solve_edo2_step(
            w_current_mm=150.0,
            precip_mm=0.0,
            t_air_c=24.0,
            rh_pct=50.0,
            slope_deg=0.0,
            crop=crop,
            is_crop=False,
            biomass_t_ha=2.0
        )
        self.assertEqual(step_trans.transpiration_mm, 0.0)
        self.assertEqual(step_trans.gamma_c_relative, 0.0)
        self.assertGreater(step_trans.evaporation_soil_mm, 0.0)
        self.assertEqual(step_trans.etc_mm, step_trans.evaporation_soil_mm)

    def test_topographic_slope_srtm_effect(self):
        """
        Criterio 3: Modulación por pendiente SRTM:
        - Infiltración efectiva se reduce por cos(theta).
        - Drenaje gravitacional lateral se acelera por sin(theta).
        Bajo idéntica precipitación y clima, una ladera empinada retiene menos agua que un llano.
        """
        crop = get_crop_parameters("frijol")
        w_start = 120.0
        p0 = 15.0
        t_air = 20.0
        rh = 65.0

        step_flat = solve_edo2_step(
            w_current_mm=w_start,
            precip_mm=p0,
            t_air_c=t_air,
            rh_pct=rh,
            slope_deg=0.0,
            crop=crop
        )

        step_slope = solve_edo2_step(
            w_current_mm=w_start,
            precip_mm=p0,
            t_air_c=t_air,
            rh_pct=rh,
            slope_deg=25.0,
            crop=crop
        )

        self.assertGreater(step_flat.infiltration_mm, step_slope.infiltration_mm)
        self.assertEqual(step_flat.drainage_mm, 0.0)
        self.assertGreater(step_slope.drainage_mm, 1.0)
        self.assertGreater(step_flat.soil_water_mm, step_slope.soil_water_mm)

    def test_irrigation_alerts_and_replenishment(self):
        """
        Criterio 4: Alertas de riego y lámina sugerida (PDF Sec. 2.6.2):
        Isugerido = (Wcc - W) / eta_riego
        Aplicar Isugerido debe compensar el déficit hídrico exactamente hacia Wcc.
        """
        crop = get_crop_parameters("maiz")
        limits = compute_soil_limits(crop, theta_fc=0.30, theta_wp=0.14)
        eta_riego = 0.85
        
        # Humedad por debajo del umbral crítico
        w_deficit = limits.w_crit - 10.0
        step_alert = solve_edo2_step(
            w_current_mm=w_deficit,
            precip_mm=0.0,
            t_air_c=22.0,
            rh_pct=60.0,
            slope_deg=0.0,
            crop=crop,
            theta_fc=0.30,
            theta_wp=0.14,
            eta_irrigation=eta_riego
        )
        self.assertTrue(step_alert.is_irrigation_needed)
        expected_lamina = round((limits.w_cc - step_alert.soil_water_mm) / eta_riego, 2)
        self.assertAlmostEqual(step_alert.suggested_irrigation_mm, expected_lamina, places=1)

        # Al aplicar la lámina Isugerido con demanda evaporativa nula (o sumando ETc)
        # se verifica la reposición exacta: W_next + ETc = Wcc
        step_replenished = solve_edo2_step(
            w_current_mm=step_alert.soil_water_mm,
            precip_mm=0.0,
            irrigation_mm=step_alert.suggested_irrigation_mm,
            t_air_c=22.0,
            rh_pct=60.0,
            slope_deg=0.0,
            crop=crop,
            theta_fc=0.30,
            theta_wp=0.14,
            eta_irrigation=eta_riego
        )
        self.assertAlmostEqual(step_replenished.soil_water_mm + step_replenished.etc_mm, limits.w_cc, delta=0.5)

    def test_crop_contrast_maiz_vs_frijol_timeseries(self):
        """
        Simulación temporal comparativa:
        Frijol (Zr = 600 mm, p = 0.45) tiene menor capacidad de retención (RAW = 43.2 mm)
        que el Maíz (Zr = 1000 mm, p = 0.55, RAW = 88 mm).
        Iniciando ambos a capacidad de campo (W0 = Wcc), Frijol entra en estrés hídrico mucho antes.
        """
        precip = [0.0] * 20
        t_air = [20.0] * 20
        rh = [55.0] * 20

        crop_maiz = get_crop_parameters("maiz")
        crop_frijol = get_crop_parameters("frijol")
        lim_maiz = compute_soil_limits(crop_maiz, 0.30, 0.14)
        lim_frijol = compute_soil_limits(crop_frijol, 0.30, 0.14)

        sim_maiz = simulate_edo2_timeseries(
            precip_series=precip,
            t_air_series=t_air,
            rh_series=rh,
            crop=crop_maiz,
            w0_mm=lim_maiz.w_cc,
            theta_fc=0.30,
            theta_wp=0.14
        )

        sim_frijol = simulate_edo2_timeseries(
            precip_series=precip,
            t_air_series=t_air,
            rh_series=rh,
            crop=crop_frijol,
            w0_mm=lim_frijol.w_cc,
            theta_fc=0.30,
            theta_wp=0.14
        )

        # Frijol entra en estrés en menos días y acumula más días en estrés
        self.assertGreater(sim_frijol["summary"]["stress_days"], sim_maiz["summary"]["stress_days"])


if __name__ == "__main__":
    unittest.main()
