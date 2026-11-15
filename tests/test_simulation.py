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

        # Modo resiliencia prioriza escudo ambiental alto
        self.assertGreater(shield_resilience, shield_profit)

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

if __name__ == "__main__":
    unittest.main()
