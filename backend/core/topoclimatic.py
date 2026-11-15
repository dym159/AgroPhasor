"""
Módulo de Downscaling Topoclimático 2.5D.
Ajusta la temperatura del aire y la radiación solar regional de NASA POWER
a cada celda local (i, j) mediante el modelo digital de elevación SRTM (30 m).
"""

import math
from typing import Tuple


def lapse_rate_air_temperature(
    t_nasa_c: float,
    cell_altitude_m: float,
    reference_altitude_m: float,
    lapse_rate_c_per_m: float = 0.0065
) -> float:
    """
    Enfriamiento adiabático por cota altitudinal SRTM (Sección 3.3):
    T_ext,i,j = T_NASA - Gamma * (z_i,j - z_ref)
    Gamma: gradiente térmico vertical estándar (~6.5 °C / 1000 m).
    """
    delta_z = cell_altitude_m - reference_altitude_m
    return t_nasa_c - (lapse_rate_c_per_m * delta_z)


def topographic_solar_factor(
    slope_rad: float,
    aspect_rad: float,
    solar_zenith_rad: float = 0.45,
    solar_azimuth_rad: float = 0.0
) -> float:
    """
    Factor geométrico de proyección solar G_i,j(theta, psi) (Sección 2.4 y 3.3).
    Ajusta la radiación recibida según la inclinación y orientación de la ladera:
    cos(incidence_angle) = cos(theta)*cos(zenith) + sin(theta)*sin(zenith)*cos(azimuth - aspect)
    """
    cos_inc = (
        math.cos(slope_rad) * math.cos(solar_zenith_rad) +
        math.sin(slope_rad) * math.sin(solar_zenith_rad) * math.cos(solar_azimuth_rad - aspect_rad)
    )
    cos_zenith = max(1e-3, math.cos(solar_zenith_rad))
    factor = max(0.0, cos_inc / cos_zenith)
    # Acotamos el factor para evitar singularidades extremas
    return min(2.0, factor)


def convert_nasa_radiation_to_wm2(rad_nasa_mj_hr: float) -> float:
    """
    Conversión obligatoria de unidades de NASA POWER:
    MJ/hr -> W/m² (Joules por segundo por metro cuadrado)
    1 MJ/hr = 10^6 J / 3600 s ≈ 277.78 W/m²
    """
    return max(0.0, rad_nasa_mj_hr * (1e6 / 3600.0))
