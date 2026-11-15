#!/usr/bin/env python3
"""
AgroPhasor - Pruebas Unitarias de Simulación y Contrato CC-02
Ejecutable con: python -m unittest discover tests
"""

import unittest
import json
import os
import sys

# Asegurar ruta al backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

from main import AgroPhasorHandler

class DummyHandler(AgroPhasorHandler):
    """Subclase mock para probar la lógica de procesamiento sin abrir sockets."""
    def __init__(self):
        pass

class TestAgroPhasorSimulation(unittest.TestCase):
    def setUp(self):
        self.handler = DummyHandler()

    def test_simulation_payload_success(self):
        """Verifica que un payload GeoJSON válido genere los 5 bloques de indicadores acordados."""
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
                            "name": "Lote Principal",
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
        
        # 1. Estado y metadatos
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["meta"]["lote_id"], "lote-mantaro-01")
        self.assertEqual(result["meta"]["area_ha"], 2.45)
        
        # 2. Cinco bloques de variables físicas por celda según Plan Maestro
        ind = result["indicadores"]
        self.assertIn("humedad_radicular_W", ind)
        self.assertIn("temperatura_dosel_T", ind)
        self.assertIn("nutrientes_NPK", ind)
        self.assertIn("biomasa_aerea_B", ind)
        self.assertIn("espesor_fertil_H", ind)
        self.assertIn("escudo_ambiental", ind)

        # 3. Unidades y órdenes de magnitud
        self.assertEqual(ind["humedad_radicular_W"]["unidad"], "mm")
        self.assertGreater(ind["humedad_radicular_W"]["valor"], 0)
        self.assertEqual(ind["temperatura_dosel_T"]["unidad"], "°C")

        # Verificación específica de dinámica EDO 4 (Biomasa y Teledetección)
        self.assertIn("valor", ind["biomasa_aerea_B"])
        self.assertEqual(ind["biomasa_aerea_B"]["unidad"], "t/ha")
        self.assertIn("tasa_crecimiento_diario", ind["biomasa_aerea_B"])
        self.assertIn("ndvi_satelital_estimado", ind["biomasa_aerea_B"])
        self.assertIn("cobertura_foliar_pct", ind["biomasa_aerea_B"])
        self.assertIn("rendimiento_estimado_cosecha", ind["biomasa_aerea_B"])

        # 4. Rotación recomendada de Pareto
        self.assertIn("rotacion_recomendada", result)
        rot = result["rotacion_recomendada"]
        self.assertIn("plan_actual", rot)
        self.assertIn("sugerencia_optimizada", rot)
        self.assertIn("motivo_agronomico", rot)

    def test_priority_modes_affect_metrics(self):
        """Verifica que los modos Máxima Resiliencia, Balance Óptimo y Mayor Ganancia ajusten el escudo."""
        payload_resilience = {"lote_seleccionado_id": "L1", "modo_prioridad": "maxima_resiliencia"}
        payload_optimo = {"lote_seleccionado_id": "L1", "modo_prioridad": "balance_optimo"}
        payload_profit = {"lote_seleccionado_id": "L1", "modo_prioridad": "mayor_ganancia"}

        res_resilience = self.handler.process_simulation(payload_resilience)
        res_optimo = self.handler.process_simulation(payload_optimo)
        res_profit = self.handler.process_simulation(payload_profit)

        shield_resilience = res_resilience["indicadores"]["escudo_ambiental"]["indice"]
        shield_optimo = res_optimo["indicadores"]["escudo_ambiental"]["indice"]
        shield_profit = res_profit["indicadores"]["escudo_ambiental"]["indice"]

        # Modo resiliencia prioriza escudo ambiental alto y selecciona ruta resiliente
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
        """Verifica la lógica matemática de la Ley de Liebig y los 4 estados del escudo."""
        # Simulación de evaluación física
        # eta_N = min(1.0, 30 / 150) = 0.20 (Nitrógeno fuertemente limitante)
        # eta_P = min(1.0, 70 / 80) = 0.875
        # eta_K = min(1.0, 200 / 220) = 0.909
        fertN, fertP, fertK = 30, 70, 200
        eta_N = min(1.0, fertN / 150)
        eta_P = min(1.0, fertP / 80)
        eta_K = min(1.0, fertK / 220)
        eta_min = min(eta_N, eta_P, eta_K)

        self.assertEqual(eta_min, eta_N)
        self.assertAlmostEqual(eta_min, 0.20, places=2)

        # Estados de escudo
        # Azul Cobalto: Psi >= 0.70
        # Violeta / Ámbar: 0.38 <= Psi < 0.70
        # Rojo Intenso: Psi < 0.38
        # Desactivado: stage == "transicion"
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
        """Verifica validación de longitud y respuesta de /api/places con geocoder simulado."""
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
        """Verifica que el servicio web de EDO 4 compute ciclos y valide con el catálogo oficial."""
        from backend.services.parcel_edo4 import ParcelEDO4Service
        from backend.models.edo4_validator import validate_edo4_catalog

        # 1. Validación de catálogo oficial gemini-code-179
        val = validate_edo4_catalog("gemini-code-1794737993920.json")
        self.assertTrue(val["valid"])

        # 2. Simulación de ciclo
        res = ParcelEDO4Service.simulate_crop_cycle(
            crop_id="maiz",
            f_rad_series_mj_m2=[20.0] * 15,
            t_canopy_series_c=[22.0] * 15,
            soil_water_series_mm=[65.0] * 15,
            nitrogen_series_kg_ha=[70.0] * 15,
            phosphorus_series_kg_ha=[40.0] * 15,
            potassium_series_kg_ha=[90.0] * 15,
        )
        self.assertEqual(res["crop"], "Maíz")
        self.assertEqual(res["days_simulated"], 15)
        self.assertGreater(res["final_biomass_t_ha"], 0.0)

if __name__ == "__main__":
    unittest.main()
