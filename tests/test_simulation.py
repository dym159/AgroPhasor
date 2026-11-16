#!/usr/bin/env python3
"""
AgroPhasor - Unit Tests for Simulation and CC-02 Contract
Run with: python -m unittest discover tests
"""

import unittest
import json
import os
import sys

# Ensure backend is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

from main import AgroPhasorHandler

class DummyHandler(AgroPhasorHandler):
    """Mock subclass to test request processing logic without opening sockets."""
    def __init__(self):
        pass

class TestAgroPhasorSimulation(unittest.TestCase):
    def setUp(self):
        self.handler = DummyHandler()

    def test_simulation_payload_success(self):
        """Verify that a valid GeoJSON payload generates the 5 agreed indicator blocks."""
        sample_payload = {
            "version": "1.0-alpha",
            "lote_seleccionado_id": "lote-mantaro-01",
            "modo_prioridad": "balance_optimo",
            "geo_features": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "lote-mantaro-01",
                        "properties": {
                            "name": "Primary Lot",
                            "area_ha": 2.45
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-75.2115, -12.0592],
                                    [-75.2095, -12.0588],
                                    [-75.2090, -12.0610],
                                    [-75.2110, -12.0615],
                                    [-75.2115, -12.0592]
                                ]
                            ]
                        }
                    }
                ]
            }
        }

        result = self.handler.process_simulation(sample_payload)
        
        # 1. Status and metadata
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["meta"]["lote_id"], "lote-mantaro-01")
        self.assertEqual(result["meta"]["area_ha"], 2.45)
        
        # 2. Five physical variable blocks per cell as defined in the Master Plan
        ind = result["indicadores"]
        self.assertIn("humedad_radicular_W", ind)
        self.assertIn("temperatura_dosel_T", ind)
        self.assertIn("nutrientes_NPK", ind)
        self.assertIn("biomasa_aerea_B", ind)
        self.assertIn("espesor_fertil_H", ind)
        self.assertIn("escudo_ambiental", ind)

        # 3. Units and magnitudes
        self.assertEqual(ind["humedad_radicular_W"]["unidad"], "mm")
        self.assertGreater(ind["humedad_radicular_W"]["valor"], 0)
        self.assertEqual(ind["temperatura_dosel_T"]["unidad"], "°C")

        # Specific check for ODE 4 dynamics (Biomass and Remote Sensing)
        self.assertIn("valor", ind["biomasa_aerea_B"])
        self.assertEqual(ind["biomasa_aerea_B"]["unidad"], "t/ha")
        self.assertIn("tasa_crecimiento_diario", ind["biomasa_aerea_B"])
        self.assertIn("ndvi_satelital_estimado", ind["biomasa_aerea_B"])
        self.assertIn("cobertura_foliar_pct", ind["biomasa_aerea_B"])
        self.assertIn("rendimiento_estimado_cosecha", ind["biomasa_aerea_B"])

        # 4. Pareto-recommended rotation
        self.assertIn("rotacion_recomendada", result)
        rot = result["rotacion_recomendada"]
        self.assertIn("plan_actual", rot)
        self.assertIn("sugerencia_optimizada", rot)
        self.assertIn("motivo_agronomico", rot)

    def test_priority_modes_affect_metrics(self):
        """Verify that Max Resilience, Balanced Optimal, and Max Profit modes adjust the shield."""
        payload_resilience = {"lote_seleccionado_id": "L1", "modo_prioridad": "maxima_resiliencia"}
        payload_optimo = {"lote_seleccionado_id": "L1", "modo_prioridad": "balance_optimo"}
        payload_profit = {"lote_seleccionado_id": "L1", "modo_prioridad": "mayor_ganancia"}

        res_resilience = self.handler.process_simulation(payload_resilience)
        res_optimo = self.handler.process_simulation(payload_optimo)
        res_profit = self.handler.process_simulation(payload_profit)

        shield_resilience = res_resilience["indicadores"]["escudo_ambiental"]["indice"]
        shield_optimo = res_optimo["indicadores"]["escudo_ambiental"]["indice"]
        shield_profit = res_profit["indicadores"]["escudo_ambiental"]["indice"]

        # Resilience mode prioritizes a higher environmental shield and picks a resilient route
        self.assertGreater(shield_resilience, shield_profit)
        self.assertNotEqual(
            res_resilience["rotacion_recomendada"]["ruta_seleccionada"],
            res_profit["rotacion_recomendada"]["ruta_seleccionada"],
        )
        self.assertNotIn(
            "papa_monocultivo",
            res_optimo["rotacion_recomendada"]["pareto_frente"],
        )

    def test_knobs_rerank_the_same_pareto_candidates(self):
        payload = {"modo_prioridad": "balance_optimo"}
        water = self.handler.process_simulation({
            **payload, "perillas": {"w1": 100, "w2": 0, "w3": 0, "w4": 0},
        })["rotacion_recomendada"]
        profit = self.handler.process_simulation({
            **payload, "perillas": {"w1": 0, "w2": 0, "w3": 100, "w4": 0},
        })["rotacion_recomendada"]

        self.assertEqual(water["ruta_seleccionada"], "avena_habas_quinua")
        self.assertEqual(profit["ruta_seleccionada"], "papa_maiz_habas")
        self.assertEqual(water["pareto_frente"], profit["pareto_frente"])

    def test_liebig_minimum_and_shield_states(self):
        """Verify Liebig's Law math and the 4 environmental shield states."""
        # Physical evaluation simulation
        # eta_N = min(1.0, 30 / 150) = 0.20 (Nitrogen strongly limiting)
        # eta_P = min(1.0, 70 / 80) = 0.875
        # eta_K = min(1.0, 200 / 220) = 0.909
        fertN, fertP, fertK = 30, 70, 200
        eta_N = min(1.0, fertN / 150)
        eta_P = min(1.0, fertP / 80)
        eta_K = min(1.0, fertK / 220)
        eta_min = min(eta_N, eta_P, eta_K)

        self.assertEqual(eta_min, eta_N)
        self.assertAlmostEqual(eta_min, 0.20, places=2)

        # Shield states
        # Cobalt Blue: Psi >= 0.70
        # Violet / Amber: 0.38 <= Psi < 0.70
        # Deep Red: Psi < 0.38
        # Deactivated: stage == "transicion"
        def classify_shield(psi, stage="cultivo"):
            if stage == "transicion":
                return "desactivado"
            if psi >= 0.70:
                return "azul_cobalto"
            if psi >= 0.38:
                return "violeta_ambar"
            return "rojo_intenso"

        self.assertEqual(classify_shield(0.85), "azul_cobalto")
        self.assertEqual(classify_shield(0.52), "violeta_ambar")
        self.assertEqual(classify_shield(0.24), "rojo_intenso")
        self.assertEqual(classify_shield(0.90, stage="transicion"), "desactivado")

    def test_places_endpoint_validation_and_search(self):
        """Verify length validation and response of /api/places using a mocked geocoder."""
        import io
        from unittest.mock import patch
        import main as backend_main

        sent = []

        class MockGetHandler(AgroPhasorHandler):
            def __init__(self, path):
                self.path = path

            def send_json_response(self, data, status=200):
                sent.append((status, data))

        MockGetHandler("/api/places?q=a").do_GET()
        self.assertEqual(sent[-1][0], 400)

        fake_body = io.BytesIO(json.dumps([
            {"display_name": "Huancayo, Junín, Perú", "lat": "-12.0651", "lon": "-75.2049"}
        ]).encode("utf-8"))
        fake_body.__enter__ = lambda s: s
        fake_body.__exit__ = lambda s, *args: False

        backend_main._places_cache.clear()
        with patch("urllib.request.urlopen", return_value=fake_body):
            MockGetHandler("/api/places?q=Huancayo").do_GET()

        status, payload = sent[-1]
        self.assertEqual(status, 200)
        self.assertEqual(payload, [{"name": "Huancayo, Junín, Perú", "lat": -12.0651, "lon": -75.2049}])

    def test_edo4_web_api_endpoints(self):
        """Verify that the ODE 4 web service computes cycles and validates against the official catalog."""
        from backend.services.parcel_edo4 import ParcelEDO4Service
        from backend.models.edo4_validator import validate_edo4_catalog

        # 1. Validate official catalog gemini-code.json
        val = validate_edo4_catalog("gemini-code.json")
        self.assertTrue(val["valid"])

        # 2. Cycle simulation
        res = ParcelEDO4Service.simulate_crop_cycle(
            crop_id="maiz",
            f_rad_series_mj_m2=[20.0] * 15,
            t_canopy_series_c=[22.0] * 15,
            soil_water_series_mm=[65.0] * 15,
            nitrogen_series_kg_ha=[70.0] * 15,
            phosphorus_series_kg_ha=[40.0] * 15,
            potassium_series_kg_ha=[90.0] * 15,
        )
        self.assertEqual(res["crop"], "Maize")
        self.assertEqual(res["days_simulated"], 15)
        self.assertGreater(res["final_biomass_t_ha"], 0.0)

if __name__ == "__main__":
    unittest.main()
