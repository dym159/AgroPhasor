"""
Catálogo de parámetros biofísicos y fisiológicos de cultivos para EDO 1 y el motor de AgroPhasor.
Valores referenciados según FAO-56 y calibraciones agrometeorológicas.
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass(frozen=True)
class CropParameters:
    name: str
    botanical_family: str
    Cp: float = 25000.0          # Capacidad calorífica foliar [J / (m² · °C)]
    hc: float = 34.0             # Coeficiente convectivo dosel-aire [W / (m² · °C)]
    alpha: float = 0.82          # Absortividad solar de vegetación (1 - albedo) [adimensional]
    lambda_gamma_max: float = 920.0  # Capacidad de refrigeración evaporativa máxima [W / (m² · kPa)]
    T_opt: float = 18.0          # Temperatura óptima de confort del cultivo [°C]
    delta_T_tol: float = 8.0     # Rango de tolerancia térmica [°C]
    T_frost: float = 2.0         # Umbral crítico de helada [°C]
    T_lethal: float = 38.0       # Umbral crítico letal de calor [°C]
    W_pmp: float = 15.0          # Umbral de marchitez permanente del suelo [mm]
    W_crit: float = 45.0         # Umbral crítico hídrico para estrés estomático [mm]
    W_fc: float = 70.0           # Capacidad de campo del suelo [mm]


# Catálogo inicial de referencia (Andes / Costa - Perú)
CROP_CATALOG: Dict[str, CropParameters] = {
    "papa": CropParameters(
        name="Papa",
        botanical_family="Solanaceae",
        Cp=24000.0,
        hc=32.0,
        alpha=0.82,
        lambda_gamma_max=920.0,
        T_opt=16.5,
        delta_T_tol=7.5,
        T_frost=1.5,
        T_lethal=35.0,
        W_pmp=18.0,
        W_crit=48.0,
        W_fc=75.0,
    ),
    "maiz": CropParameters(
        name="Maíz",
        botanical_family="Poaceae",
        Cp=28000.0,
        hc=36.0,
        alpha=0.80,
        lambda_gamma_max=950.0,
        T_opt=22.0,
        delta_T_tol=9.0,
        T_frost=4.0,
        T_lethal=42.0,
        W_pmp=15.0,
        W_crit=42.0,
        W_fc=70.0,
    ),
    "haba": CropParameters(
        name="Haba",
        botanical_family="Fabaceae",
        Cp=22000.0,
        hc=30.0,
        alpha=0.83,
        lambda_gamma_max=900.0,
        T_opt=15.0,
        delta_T_tol=7.0,
        T_frost=0.0,
        T_lethal=32.0,
        W_pmp=16.0,
        W_crit=45.0,
        W_fc=72.0,
    ),
    "barbecho": CropParameters(
        name="Suelo Desnudo / Transición",
        botanical_family="None",
        Cp=35000.0,              # Capacidad calorífica del suelo desnudo
        hc=40.0,
        alpha=0.75,
        lambda_gamma_max=0.0,     # Sin transpiración estomática vegetal
        T_opt=20.0,
        delta_T_tol=15.0,
        T_frost=-5.0,
        T_lethal=50.0,
        W_pmp=0.0,
        W_crit=0.0,
        W_fc=70.0,
    ),
}


def get_crop_parameters(crop_id: str) -> CropParameters:
    key = crop_id.strip().lower()
    return CROP_CATALOG.get(key, CROP_CATALOG["papa"])
