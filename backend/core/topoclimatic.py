"""
2.5D Topoclimatic Downscaling Module.
Adjusts regional NASA POWER air temperature and solar radiation to each local cell (i, j)
using the SRTM 30 m digital elevation model.
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
    Adiabatic lapse-rate cooling by SRTM elevation (Section 3.3):
    T_ext,i,j = T_NASA - Gamma * (z_i,j - z_ref)
    Gamma: standard vertical thermal gradient (~6.5 °C / 1000 m).
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
    Geometric solar projection factor G_i,j(theta, psi) (Sections 2.4 and 3.3).
    Adjusts received irradiance according to hillslope inclination and aspect:
    cos(incidence_angle) = cos(theta)*cos(zenith) + sin(theta)*sin(zenith)*cos(azimuth - aspect)
    """
    cos_inc = (
        math.cos(slope_rad) * math.cos(solar_zenith_rad) +
        math.sin(slope_rad) * math.sin(solar_zenith_rad) * math.cos(solar_azimuth_rad - aspect_rad)
    )
    cos_zenith = max(1e-3, math.cos(solar_zenith_rad))
    factor = max(0.0, cos_inc / cos_zenith)
    # Bound the projection factor to avoid extreme singularities
    return min(2.0, factor)


def convert_nasa_radiation_to_wm2(rad_nasa_mj_hr: float) -> float:
    """
    Required unit conversion from NASA POWER hourly irradiance:
    MJ/hr -> W/m² (Joules per second per square meter)
    1 MJ/hr = 10^6 J / 3600 s ≈ 277.78 W/m²
    """
    return max(0.0, rad_nasa_mj_hr * (1e6 / 3600.0))
