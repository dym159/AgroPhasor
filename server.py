#!/usr/bin/env python3
"""
AgroPhasor - Local Execution Entry Point
Serves the frontend web application and REST API at http://127.0.0.1:5173
"""
import sys
import os

backend_path = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_path)

from main import run

if __name__ == "__main__":
    run()
