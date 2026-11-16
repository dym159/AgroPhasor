"""
Unit Test Suite for ODE 3: Vector Macronutrient Dynamics (AgroPhasor).
Verifies:
1. Strict validation of the JSON parameter catalog for ODE 3.
2. Unconditional biogeochemical non-negativity boundary and numerical stability (N, P, K >= 0).
3. Biological recharge via symbiotic Nitrogen fixation in Legumes (Dry Bean vs Maize).
4. Phosphorus conservation (immune to vertical leaching) and surface runoff erosion loss.
5. Potassium recycling from stover decomposition during bare-soil transition.
6. Scalar fertility projection using Liebig's Law of the Minimum and limiting-nutrient detection.
7. Multi-stage rotation simulation in ParcelEDO3Service.
8. ODE 3 integration with the web app simulation contract payload.
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
        """Verify that gemini-code-1794737993920.json is 100% valid for ODE 3."""
        self.assertTrue(os.path.exists(JSON_PATH), f"File does not exist: {JSON_PATH}")
        
        result = validate_edo3_catalog(JSON_PATH)
        self.assertTrue(result["valid"], f"JSON validation failed: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertGreaterEqual(result["crops_validated_count"], 2)
        
        # Global constants required by ODE 3
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
        
        # Maize parameters
        crops = result["crops_summary"]
        self.assertIn("Maiz_Zea_mays", crops)
        maiz = crops["Maiz_Zea_mays"]
        self.assertFalse(maiz["es_fijador_N"])
        self.assertEqual(maiz["F_fix"], 0.0)
        self.assertEqual(maiz["Liebig_K_N"], 35.0)
        self.assertEqual(maiz["Liebig_K_P"], 18.0)
        self.assertEqual(maiz["Liebig_K_K"], 45.0)
        
        # Dry Bean parameters
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
        Criterion 1: Unconditional non-negativity and matrix stability.
        Even under extreme nutrient depletion, N, P, and K remain strictly non-negative.
        """
        crop_maiz = get_crop_parameters("maiz")
        soil = SoilChemicalProperties(om_pct=0.5, cic_cmolc_kg=5.0, ph=7.0, ec_ds_m=1.0)
        
        step_out = solve_edo3_step(
            n_current_kg_ha=0.5,
            p_current_kg_ha=0.2,
            k_current_kg_ha=1.0,
            w_mm=250.0,      # Extreme waterlogging
            w_cc_mm=100.0,
            t_soil_c=35.0,   # High soil temperature
            crop=crop_maiz,
            soil=soil,
            erosion_rate_mm_day=5.0,  # Severe erosion
            is_crop=True,
            dt_days=10.0     # Long integration step
        )
        self.assertGreaterEqual(step_out.n_kg_ha, 0.0)
        self.assertGreaterEqual(step_out.p_kg_ha, 0.0)
        self.assertGreaterEqual(step_out.k_kg_ha, 0.0)
        self.assertGreaterEqual(step_out.eta_nutrientes, 0.0)
        self.assertLessEqual(step_out.eta_nutrientes, 1.0)

    def test_biological_nitrogen_fixation_legume_vs_cereal(self):
        """
        Criterion 2: Biological Nitrogen fixation.
        A legume (Dry Bean, F_fix > 0) generates active biological input (SN_fix > 0),
        whereas a cereal (Maize, F_fix = 0) fixes no nitrogen.
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
        self.assertAlmostEqual(step_frijol.biological_n_fixation_kg, crop_frijol.F_fix * crop_frijol.B_max_t_ha * .40, places=3)
        self.assertGreater(step_frijol.n_kg_ha, step_maiz.n_kg_ha)

    def test_phosphorus_solubilization_and_erosion_loss(self):
        """
        Criterion 3: Phosphorus dynamics:
        - Immune to vertical leaching.
        - Susceptible to surface runoff erosion drag dH/dt.
        """
        crop = get_crop_parameters("frijol")
        soil = SoilChemicalProperties()

        # Case with no erosion
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

        # Case with strong surface erosion (bare hillside)
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
        Criterion 4: Potassium recycling from crop residue.
        When is_crop=False (transition/fallow regime), the term
        SK_res = beta_K * k_dec * B activates, releasing potassium back into the soil.
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
        self.assertAlmostEqual(step_trans.k_stover_recycling_kg, 0.65 * 0.025 * 3.0, places=3)

    def test_liebig_minimum_and_limiting_nutrient(self):
        """
        Criterion 5: Liebig's Law of the Minimum.
        The global factor eta_nutrientes equals min(e_N, e_P, e_K)
        and accurately identifies whichever nutrient limits crop yield.
        """
        # Case 1: N limiting
        eta1, lim1, comp1 = compute_liebig_factor(15.0, 50.0, 150.0, kn=35.0, kp=18.0, kk=45.0)
        self.assertEqual(lim1, "N")
        self.assertAlmostEqual(eta1, 15.0 / (15.0 + 35.0), places=2)

        # Case 2: P limiting
        eta2, lim2, comp2 = compute_liebig_factor(80.0, 5.0, 150.0, kn=35.0, kp=18.0, kk=45.0)
        self.assertEqual(lim2, "P")
        self.assertAlmostEqual(eta2, 5.0 / (5.0 + 18.0), places=2)

        # Case 3: K limiting
        eta3, lim3, comp3 = compute_liebig_factor(80.0, 50.0, 10.0, kn=35.0, kp=18.0, kk=45.0)
        self.assertEqual(lim3, "K")
        self.assertAlmostEqual(eta3, 10.0 / (10.0 + 45.0), places=2)

    def test_multi_stage_rotation_service(self):
        """
        Multi-stage rotation simulation in ParcelEDO3Service:
        Stage 1: Maize (120 days, high nutrient uptake)
        Stage 2: Transition (30 days, residue decomposition)
        Stage 3: Dry Bean (90 days, biological N fixation)
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
        # Dry Bean stage must have fixed nitrogen
        self.assertGreater(res["stages"][2]["n_fixed_kg_ha"], 5.0)
        # Transition stage must have recycled potassium
        self.assertGreater(res["stages"][1]["k_recycled_kg_ha"], 0.0)
        # Trajectories must be complete
        self.assertEqual(len(res["trajectories"]["n_series"]), 96)

    def test_api_simulation_payload_includes_dynamic_edo3(self):
        """
        Verify that the /api/v1/simular endpoint responds with ODE 3 fields
        to drive the WebGL / 2.5D frontend and the Liebig health bar.
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
