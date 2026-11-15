#!/usr/bin/env python3
"""
AgroPhasor - Acceso Directo de Ejecución Local
Inicia el servidor backend y sirve la aplicación frontend en http://localhost:8000
"""
import sys
import os

backend_path = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_path)

from main import run

if __name__ == "__main__":
    run()
