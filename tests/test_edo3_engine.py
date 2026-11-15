"""
Suite de Pruebas Unitarias para EDO 3: Dinámica Vectorial de Macronutrientes (AgroPhasor).
Verifica:
1. Validación estricta del catálogo JSON de parámetros para EDO 3.
2. Frontera biogeoquímica de no-negatividad incondicional y estabilidad numérica (N, P, K >= 0).
3. Recarga biológica por fijación simbiótica de Nitrógeno en Leguminosas (Frijol vs Maíz).
4. Conservación de Fósforo (inmune a lixiviación vertical) y pérdida por erosión superficial.
5. Reciclaje de Potasio a partir de la descomposición de rastrojos durante la transición.
6. Proyección escalar de fertilidad mediante la Ley del Mínimo de Liebig e identificación del limitante.
7. Simulación de rotación multietapa en ParcelEDO3Service.
8. Integración de EDO 3 con el payload del contrato de simulación de la app web.
"""

import math
import os
import unittest

from backend.models.edo3_validator import validate_edo3_catalog, EDO3ValidationError
from backend.models.crop_parameters import get_crop_parameters, CropParameters
from backend.core.edo3_engine import (
    solve_edo3_step,
    simulate_edo3_timeseries,
    compute_liebig_factor,
    calculate_phi_ph_ec,
    microbial_temperature_factor,
    SoilChemicalProperties,
    EDO3StepOutput
)
from backend.services.parcel_edo3 import ParcelEDO3Service
from backend.main import compute_simulation_payload

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "gemini-code-1794737993920.json")


class TestEDO3Engine(unittest.TestCase):

    def test_json_catalog_validation_success(self):
        """Verifica que gemini-code-1794737993920.json sea 100% válido para EDO 3."""
        self.assertTrue(os.path.exists(JSON_PATH), f"No existe el archivo {JSON_PATH}")
        
        result = validate_edo3_catalog(JSON_PATH)
        self.assertTrue(result["valid"], f"Falló validación de JSON: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertGreaterEqual(result["crops_validated_count"], 2)
        
        # Constantes globales requeridas por EDO 3
        global_p = result["global_parameters_edo3"]
        self.assertAlmostEqual(global_p["k_min0_dia"], 0.0018)
        self.assertAlmostEqual(global_p["Q10"], 2.0)
        self.assertAlmostEqual(global_p["k_lN"], 0.035)
        self.assertAlmostEqual(global_p["k_lK"], 0.015)
        self.assertAlmostEqual(global_p["beta_K"], 0.65)
        self.assertAlmostEqual(global_p["k_dec_dia"], 0.025)
        self.assertAlmostEqual(global_p["xi_N"], 0.004)
        self.assertAlmostEqual(global_p["xi_P"], 0.008)
        self.assertAlmostEqual(global_p["xi_K"], 0.003)
        
        # Parámetros de Maíz
        crops = result["crops_summary"]
        self.assertIn("Maiz_Zea_mays", crops)
        maiz = crops["Maiz_Zea_mays"]
        self.assertFalse(maiz["es_fijador_N"])
        self.assertEqual(maiz["F_fix"], 0.0)
        self.assertEqual(maiz["Liebig_K_N"], 35.0)
        self.assertEqual(maiz["Liebig_K_P"], 18.0)
        self.assertEqual(maiz["Liebig_K_K"], 45.0)
        
        # Parámetros de Frijol
        self.assertIn("Frijol_Phaseolus_vulgaris", crops)
        frijol = crops["Frijol_Phaseolus_vulgaris"]
        self.assertTrue(frijol["es_fijador_N"])
        self.assertEqual(frijol["F_fix"], 0.14)
        self.assertEqual(frijol["F_sol"], 0.05)
        self.assertEqual(frijol["Liebig_K_N"], 20.0)
        self.assertEqual(frijol["Liebig_K_P"], 22.0)
        self.assertEqual(frijol["Liebig_K_K"], 35.0)

    def test_unconditional_non_negativity_and_matrix_stability(self):
        """
        Criterio 1: No-negatividad incondicional y estabilidad matricial.
        Incluso con agotamiento extremo, N, P y K se mantienen estrictamente no-negativos.
        """
        crop_maiz = get_crop_parameters("maiz")
        soil = SoilChemicalProperties(om_pct=0.5, cic_cmolc_kg=5.0, ph=7.0, ec_ds_m=1.0)
        
        step_out = solve_edo3_step(
            n_current_kg_ha=0.5,
            p_current_kg_ha=0.2,
            k_current_kg_ha=1.0,
            w_mm=250.0,      # Inundación extrema
            w_cc_mm=100.0,
            t_soil_c=35.0,   # Alta temperatura
            crop=crop_maiz,
            soil=soil,
            erosion_rate_mm_day=5.0,  # Fuerte erosión
            is_crop=True,
            dt_days=10.0     # Paso de integración largo
        )
        self.assertGreaterEqual(step_out.n_kg_ha, 0.0)
        self.assertGreaterEqual(step_out.p_kg_ha, 0.0)
        self.assertGreaterEqual(step_out.k_kg_ha, 0.0)
        self.assertGreaterEqual(step_out.eta_nutrientes, 0.0)
        self.assertLessEqual(step_out.eta_nutrientes, 1.0)

    def test_biological_nitrogen_fixation_legume_vs_cereal(self):
        """
        Criterio 2: Fijación biológica de Nitrógeno.
        Una leguminosa (Frijol, F_fix > 0) genera aporte biológico activo (SN_fix > 0),
        mientras que un cereal (Maíz, F_fix = 0) no fija nitrógeno.
        """
        crop_maiz = get_crop_parameters("maiz")
        crop_frijol = get_crop_parameters("frijol")
        soil = SoilChemicalProperties(om_pct=2.5, cic_cmolc_kg=20.0)

        step_maiz = solve_edo3_step(
            n_current_kg_ha=50.0,
            p_current_kg_ha=30.0,
            k_current_kg_ha=150.0,
            w_mm=80.0,
            w_cc_mm=120.0,
            t_soil_c=22.0,
            crop=crop_maiz,
            soil=soil,
            is_crop=True
        )

        step_frijol = solve_edo3_step(
            n_current_kg_ha=50.0,
            p_current_kg_ha=30.0,
            k_current_kg_ha=150.0,
            w_mm=80.0,
            w_cc_mm=120.0,
            t_soil_c=22.0,
            crop=crop_frijol,
            soil=soil,
            is_crop=True
        )

        self.assertEqual(step_maiz.biological_n_fixation_kg, 0.0)
        self.assertGreater(step_frijol.biological_n_fixation_kg, 0.5)
        self.assertGreater(step_frijol.n_kg_ha, step_maiz.n_kg_ha)

    def test_phosphorus_solubilization_and_erosion_loss(self):
        """
        Criterio 3: Dinámica de Fósforo:
        - Inmune a lixiviación vertical.
        - Sensible al arrastre por erosión hídrica superficial dH/dt.
        """
        crop = get_crop_parameters("frijol")
        soil = SoilChemicalProperties()

        # Caso sin erosión
        step_no_eros = solve_edo3_step(
            n_current_kg_ha=80.0,
            p_current_kg_ha=30.0,
            k_current_kg_ha=160.0,
            w_mm=100.0,
            w_cc_mm=120.0,
            t_soil_c=20.0,
            crop=crop,
            soil=soil,
            erosion_rate_mm_day=0.0
        )
        self.assertEqual(step_no_eros.erosion_loss_p_kg, 0.0)

        # Caso con fuerte erosión superficial (ladera desnuda)
        step_with_eros = solve_edo3_step(
            n_current_kg_ha=80.0,
            p_current_kg_ha=30.0,
            k_current_kg_ha=160.0,
            w_mm=100.0,
            w_cc_mm=120.0,
            t_soil_c=20.0,
            crop=crop,
            soil=soil,
            erosion_rate_mm_day=2.5
        )
        self.assertGreater(step_with_eros.erosion_loss_p_kg, 0.1)
        self.assertLess(step_with_eros.p_kg_ha, step_no_eros.p_kg_ha)

    def test_potassium_stover_recycling_in_transition(self):
        """
        Criterio 4: Reciclaje de Potasio en rastrojo.
        Cuando is_crop=False (régimen de transición/barbecho), se activa el término
        SK_res = beta_K * k_dec * B, liberando potasio al suelo.
        """
        crop = get_crop_parameters("maiz")
        soil = SoilChemicalProperties()

        step_crop = solve_edo3_step(
            n_current_kg_ha=80.0,
            p_current_kg_ha=30.0,
            k_current_kg_ha=120.0,
            w_mm=80.0,
            w_cc_mm=120.0,
            t_soil_c=20.0,
            crop=crop,
            soil=soil,
            is_crop=True,
            biomass_t_ha=3.0
        )

        step_trans = solve_edo3_step(
            n_current_kg_ha=80.0,
            p_current_kg_ha=30.0,
            k_current_kg_ha=120.0,
            w_mm=80.0,
            w_cc_mm=120.0,
            t_soil_c=20.0,
            crop=crop,
            soil=soil,
            is_crop=False,
            biomass_t_ha=3.0
        )

        self.assertEqual(step_crop.k_stover_recycling_kg, 0.0)
        self.assertGreater(step_trans.k_stover_recycling_kg, 0.5)

    def test_liebig_minimum_and_limiting_nutrient(self):
        """
        Criterio 5: Ley del Mínimo de Liebig.
        El factor global eta_nutrientes es el mínimo de (e_N, e_P, e_K)
        e identifica con precisión el nutriente que limita el rendimiento.
        """
        # Caso 1: N limitante
        eta1, lim1, comp1 = compute_liebig_factor(15.0, 50.0, 150.0, kn=35.0, kp=18.0, kk=45.0)
        self.assertEqual(lim1, "N")
        self.assertAlmostEqual(eta1, 15.0 / (15.0 + 35.0), places=2)

        # Caso 2: P limitante
        eta2, lim2, comp2 = compute_liebig_factor(80.0, 5.0, 150.0, kn=35.0, kp=18.0, kk=45.0)
        self.assertEqual(lim2, "P")
        self.assertAlmostEqual(eta2, 5.0 / (5.0 + 18.0), places=2)

        # Caso 3: K limitante
        eta3, lim3, comp3 = compute_liebig_factor(80.0, 50.0, 10.0, kn=35.0, kp=18.0, kk=45.0)
        self.assertEqual(lim3, "K")
        self.assertAlmostEqual(eta3, 10.0 / (10.0 + 45.0), places=2)

    def test_multi_stage_rotation_service(self):
        """
        Simulación de rotación multietapa en ParcelEDO3Service:
        Etapa 1: Maíz (120 días, alta extracción)
        Etapa 2: Transición (30 días, descomposición de rastrojo)
        Etapa 3: Frijol (90 días, fijación biológica de N)
        """
        stages = [
            {"crop_id": "maiz", "duration_days": 40, "is_crop": True},
            {"crop_id": "transicion", "duration_days": 15, "is_crop": False},
            {"crop_id": "frijol", "duration_days": 40, "is_crop": True}
        ]
        w_series = [85.0] * 95
        t_soil_series = [19.0] * 95

        res = ParcelEDO3Service.simulate_rotation(
            stages=stages,
            t_soil_series=t_soil_series,
            w_series=w_series,
            om_pct=3.0,
            cic_cmolc_kg=22.0,
            n0_kg_ha=80.0,
            p0_kg_ha=30.0,
            k0_kg_ha=160.0
        )

        self.assertEqual(len(res["stages"]), 3)
        # La etapa de frijol debe haber fijado nitrógeno
        self.assertGreater(res["stages"][2]["n_fixed_kg_ha"], 5.0)
        # La etapa de transición debe haber reciclado potasio
        self.assertGreater(res["stages"][1]["k_recycled_kg_ha"], 1.0)
        # Las trayectorias deben estar completas
        self.assertEqual(len(res["trajectories"]["n_series"]), 96)

    def test_api_simulation_payload_includes_dynamic_edo3(self):
        """
        Verifica que el endpoint /api/v1/simular responda con los campos
        de EDO 3 para alimentar el frontend WebGL / 2.5D y la barra de Liebig.
        """
        payload = {
            "lote_seleccionado_id": "lote-test-01",
            "modo_prioridad": "maxima_resiliencia",
            "activar_edo3": True,
            "soil_om_pct": 3.2,
            "soil_cic": 24.0,
            "soil_ph": 6.8
        }
        res = compute_simulation_payload(payload)
        self.assertEqual(res["status"], "success")
        
        npk = res["indicadores"]["nutrientes_NPK"]
        self.assertIn("N", npk)
        self.assertIn("P", npk)
        self.assertIn("K", npk)
        self.assertIn("eta_nutrientes", npk)
        self.assertIn("nutriente_limitante", npk)
        self.assertIn("fijacion_biologica_activa", npk)
        self.assertTrue(npk["fijacion_biologica_activa"])
        self.assertGreater(npk["eta_nutrientes"], 0.60)


if __name__ == "__main__":
    unittest.main()
