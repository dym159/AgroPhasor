"""
Unit Test Suite for ODE 5: Topsoil Water Erosion (AgroPhasor).
Verifies:
1. Strict validation of the JSON parameter catalog for ODE 5 (gemini-code-1794737993920.json).
2. Criterion 1: Flat terrain (slope theta = 0°) yields strictly zero erosion (dH/dt = 0).
3. Criterion 2: SRTM topographic modulation increasing monotonically with sin(theta).
4. Criterion 3: Exponential mechanical shield from leaf biomass and residue exp(-lambda_B * B).
5. Criterion 4: Transition/tillage erodibility switch (k_er,tillage vs k_er,crop, exact 8.75x jump).
6. Criterion 5: Physical conservation bounds, irreversibility (dH/dt <= 0), and non-negativity (bedrock H >= 0).
7. Criterion 6: Edaphic coupling with ODE 2 (Wcc collapse) and mechanical phosphorus drag in ODE 3.
8. Criterion 7: Pareto soil-conservation metric f2 calculation and 3D rendering cues.
9. Criterion 8: 2.5D spatial simulation with critical hillside cell (hotspot) detection.
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
JSON_PATH = os.path.join(BASE_DIR, "gemini-code-1794737993920.json")


class TestEDO5Engine(unittest.TestCase):

    def test_json_catalog_validation_success(self):
        """Verify that gemini-code-1794737993920.json is 100% valid for ODE 5."""
        self.assertTrue(os.path.exists(JSON_PATH), f"File does not exist: {JSON_PATH}")
        
        result = validate_edo5_catalog(JSON_PATH)
        self.assertTrue(result["valid"], f"JSON validation failed: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertGreaterEqual(result["crops_validated_count"], 2)
        
        # Verify global constants for ODE 5
        global_p = result["global_parameters_edo5"]
        self.assertAlmostEqual(global_p["k_er_cultivo"], 0.0004)
        self.assertAlmostEqual(global_p["k_er_labranza"], 0.0035)
        self.assertAlmostEqual(global_p["lambda_B_ha_t"], 0.45)
        self.assertAlmostEqual(global_p["xi_N"], 0.004)
        self.assertAlmostEqual(global_p["xi_P"], 0.008)
        self.assertAlmostEqual(global_p["xi_K"], 0.003)
        
        # Verify crop canopy soil protection
        crops = result["crops_summary"]
        self.assertIn("Maiz_Zea_mays", crops)
        self.assertIn("Frijol_Phaseolus_vulgaris", crops)
        
        # Maize: B_max = 22 t/ha -> canopy protection > 99.9%
        maiz = crops["Maiz_Zea_mays"]
        self.assertEqual(maiz["B_max_t_ha"], 22.0)
        self.assertGreater(maiz["soil_protection_peak_pct"], 99.9)
        
        # Dry Bean: B_max = 7.5 t/ha -> canopy protection > 96%
        frijol = crops["Frijol_Phaseolus_vulgaris"]
        self.assertEqual(frijol["B_max_t_ha"], 7.5)
        self.assertGreater(frijol["soil_protection_peak_pct"], 96.0)

    def test_json_catalog_validation_catches_invalid_parameters(self):
        """Verify that the validator rejects catalogs with physical inconsistencies."""
        # Case 1: k_er_labranza <= k_er_cultivo (physical violation)
        bad_catalog_1 = {
            "constantes_globales": {
                "k_er_cultivo": 0.005,
                "k_er_labranza": 0.001,  # Lower than crop: impossible
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
        self.assertTrue(any("Physical inconsistency" in e for e in res_1["errors"]))

        # Case 2: Negative parameters
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
        Criterion 1: On horizontal terrain (theta = 0°), sin(theta) = 0.
        The erosion rate must be mathematically zero regardless of rain intensity
        or completely bare soil.
        """
        h_initial = 400.0  # mm
        step = solve_edo5_step(
            h_current_mm=h_initial,
            precip_mm=95.0,        # Severe 95 mm/day storm (GPM/IMERG)
            slope_deg=0.0,         # Flat terrain (SRTM)
            biomass_t_ha=0.0,      # Completely bare soil
            is_transition=True,    # Critical tillage window
            h_initial_mm=h_initial
        )
        self.assertEqual(step.dh_dt_mm_day, 0.0)
        self.assertEqual(step.erosion_loss_step_mm, 0.0)
        self.assertEqual(step.h_current_mm, h_initial)
        self.assertEqual(step.topographic_factor_sin, 0.0)

    def test_criterion_2_slope_monotonicity_srtm(self):
        """
        Criterion 2: With steeper SRTM topographic slope, flow shear stress
        increases strictly with sin(theta).
        theta_flat (0°) < theta_gentle (3°) < theta_hillside (12°) < theta_steep (30°)
        """
        precip = 50.0  # mm/day
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
        Criterion 3: Exponential attenuation of raindrop impact by canopy biomass and residue:
        protection_factor = exp(-lambda_B * B).
        A dense crop (Maize at B = 20 t/ha) cuts erosion by over 99.9% compared to bare soil.
        """
        precip = 60.0
        slope = 15.0  # Steep hillside
        lambda_b = 0.45

        # Case A: Bare soil (B = 0)
        step_bare = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=0.0, is_transition=False, lambda_b=lambda_b
        )
        self.assertAlmostEqual(step_bare.vegetation_cover_factor, 1.0)

        # Case B: Emerging crop (B = 2 t/ha)
        step_young = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=2.0, is_transition=False, lambda_b=lambda_b
        )
        self.assertAlmostEqual(step_young.vegetation_cover_factor, math.exp(-0.45 * 2.0), places=3)
        self.assertLess(step_young.erosion_loss_step_mm, step_bare.erosion_loss_step_mm)

        # Case C: Closed-canopy high-biomass crop (B = 20 t/ha)
        step_dense = solve_edo5_step(
            h_current_mm=400.0, precip_mm=precip, slope_deg=slope,
            biomass_t_ha=20.0, is_transition=False, lambda_b=lambda_b
        )
        expected_factor = math.exp(-0.45 * 20.0)  # ≈ 0.000123
        self.assertAlmostEqual(step_dense.vegetation_cover_factor, expected_factor, places=4)
        
        # Reduction > 99.9%
        efficiency = (1.0 - (step_dense.erosion_loss_step_mm / step_bare.erosion_loss_step_mm)) * 100.0
        self.assertGreater(efficiency, 99.9)

    def test_criterion_4_tillage_transition_jump(self):
        """
        Criterion 4: Discrete jump when switching to q(t) = Transition (tillage / disturbed soil).
        k_er switches from k_er,crop (0.0004) to k_er,tillage (0.0035).
        Soil vulnerability multiplies by an exact factor of 8.75x.
        """
        precip = 40.0
        slope = 10.0
        biomass = 0.5  # Minimal crop residue

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
        self.assertAlmostEqual(ratio, 0.0035 / 0.0004, places=2)  # Exactly 8.75
        self.assertEqual(step_labranza.erodibility_k_er, 0.0035)
        self.assertEqual(step_cultivo.erodibility_k_er, 0.0004)

    def test_criterion_5_non_negativity_and_irreversibility(self):
        """
        Criterion 5: Physical boundaries:
        - Irreversibility: dH/dt <= 0 always.
        - Strict non-negativity: H cannot drop below 0 (bedrock cutoff).
        """
        h_initial = 10.0  # Shallow degraded topsoil
        # Simulate a catastrophic storm event
        step_over = solve_edo5_step(
            h_current_mm=2.0,
            precip_mm=1000.0,
            slope_deg=45.0,
            biomass_t_ha=0.0,
            is_transition=True,
            h_initial_mm=h_initial
        )
        # H must clamp exactly at 0
        self.assertEqual(step_over.h_current_mm, 0.0)
        self.assertEqual(step_over.soil_retention_ratio, 0.0)
        self.assertTrue(step_over.is_bedrock_exposed)
        self.assertLessEqual(step_over.dh_dt_mm_day, 0.0)

        # Once at 0, no further erosion can occur
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
        Criterion 6: Physical coupling with the other subsystems:
        - As H shrinks, ODE 2 water retention collapses: Wcc(H) = theta_fc * H.
        - Mechanical drag of macronutrients in ODE 3: xi * Delta_H * Nutrient (especially Phosphorus).
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
        # Wcc must shrink synchronously
        expected_w_cc = round(theta_fc * step.h_current_mm, 2)
        self.assertAlmostEqual(step.w_cc_mm, expected_w_cc)
        
        # Phosphorus drag loss must be positive
        p_loss = step.nutrient_drag_kg_ha["P"]
        self.assertGreater(p_loss, 0.0)
        expected_p_loss = round(0.008 * step.erosion_loss_step_mm * nutrients["P"], 4)
        self.assertAlmostEqual(p_loss, expected_p_loss)

    def test_criterion_7_pareto_metric_f2_and_visual_subsidence(self):
        """
        Criterion 7: Cost function f2 evaluation (Best Soil at the End)
        and 3D visualization (vertex subsidence and brown-to-gray soil color shift).
        """
        # Comparison of two rotations:
        # Rotation A (Conservationist): final H = 390 mm out of 400 mm (2.5% loss), fertility eta_N = 0.85
        f2_cons = compute_soil_pareto_metric_f2(
            h_initial=400.0, h_final=390.0, chemical_health_eta_n=0.85, omega_h=0.5, omega_n=0.5
        )
        
        # Rotation B (Erosive with heavy tillage during rains): final H = 300 mm (25% loss), eta_N = 0.40
        f2_eros = compute_soil_pareto_metric_f2(
            h_initial=400.0, h_final=300.0, chemical_health_eta_n=0.40, omega_h=0.5, omega_n=0.5
        )
        
        # Under Pareto formulation (degradation minimization), f2_cons < f2_eros
        self.assertLess(f2_cons, f2_eros)
        self.assertAlmostEqual(f2_cons, 0.5 * (10.0 / 400.0) + 0.5 * (1.0 - 0.85), places=3)
        self.assertAlmostEqual(f2_eros, 0.5 * (100.0 / 400.0) + 0.5 * (1.0 - 0.40), places=3)

        # Color verification: fertile brown for healthy soil, gray for degraded
        color_intact = compute_soil_color(retention_ratio=1.0)
        color_ruined = compute_soil_color(retention_ratio=0.0)
        self.assertEqual(color_intact, (101, 67, 33))   # Fertile brown
        self.assertEqual(color_ruined, (128, 128, 128)) # Rocky gray

    def test_criterion_8_parcel_edo5_spatial_service(self):
        """
        Criterion 8: 2.5D multi-cell spatial simulation.
        Verifies that the steepest cell on the hillside is identified as the critical erosion hotspot.
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
        
        # Verify loss ordering by slope
        cell_dict = {c["cell_id"]: c["erosion_loss_mm"] for c in res["cells"]}
        self.assertLess(cell_dict["c_plano"], cell_dict["c_ladera_media"])
        self.assertLess(cell_dict["c_ladera_media"], cell_dict["c_ladera_pronunciada"])


if __name__ == "__main__":
    unittest.main()
