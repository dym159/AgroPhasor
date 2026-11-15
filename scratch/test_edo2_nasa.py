import urllib.request
import json
import math
import numpy as np

def fetch_nasa_data(lat=-12.06, lon=-75.21, start="20230101", end="20230131"):
    """
    Obtiene series de tiempo diarias de NASA POWER:
    - PRECTOTCORR: Precipitación corregida (mm/día)
    - T2M: Temperatura media a 2m (°C)
    - RH2M: Humedad relativa a 2m (%)
    - ALLSKY_SFC_SW_DWN: Radiación solar incidente (MJ/m2/día)
    - GWETROOT: Humedad del suelo en zona radicular (0-1) modelo MERRA-2/SMAP
    """
    url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point?"
        f"parameters=PRECTOTCORR,T2M,RH2M,ALLSKY_SFC_SW_DWN,GWETROOT&community=AG&"
        f"longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON"
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'AgroPhasor-EDO2/1.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    return data['properties']['parameter']

class SoilHydrologyEDO2:
    def __init__(self, 
                 theta_fc=0.32,      # Capacidad de campo (m3/m3 - Franco arcilloso de SSURGO/WSS)
                 theta_wp=0.15,      # Punto de marchitez permanente (m3/m3)
                 H_soil=400.0,       # Profundidad radicular efectiva Zr / espesor (mm)
                 slope_deg=10.0,     # Pendiente SRTM (grados)
                 p_c=0.50,           # Fracción de agotamiento permisible (FAO 56)
                 gamma_max=1.8,      # Conductancia estomática / factor transpirativo max (mm/(kPa*día))
                 E_suelo_0=2.0,      # Evaporación basal de suelo descubierta (mm/día)
                 lambda_B=0.4,       # Extinción de radiación por biomasa foliar
                 B=3.5,              # Biomasa aérea (t/ha)
                 kd=0.04,            # Coeficiente de drenaje gravitacional dependiente de ladera
                 eta_riego=0.85):    # Eficiencia de riego por goteo/aspersión
        
        self.H_soil = H_soil
        self.theta_fc = theta_fc
        self.theta_wp = theta_wp
        self.W_cc = theta_fc * H_soil   # ej: 0.32 * 400 = 128 mm
        self.W_pmp = theta_wp * H_soil  # ej: 0.15 * 400 = 60 mm
        self.p_c = p_c
        # Umbral crítico de estrés hídrico (Wcrit)
        self.W_crit = self.W_cc - self.p_c * (self.W_cc - self.W_pmp) # 128 - 0.5*(68) = 94 mm
        
        self.slope_rad = math.radians(slope_deg)
        self.cos_theta = math.cos(self.slope_rad)
        self.sin_theta = math.sin(self.slope_rad)
        
        self.gamma_max = gamma_max
        self.E_suelo_0 = E_suelo_0
        self.lambda_B = lambda_B
        self.B = B
        self.kd = kd
        self.eta_riego = eta_riego

    def vpd_kpa(self, T_air, rh):
        # Fórmula de Tetens
        es = 0.6108 * math.exp((17.27 * T_air) / (T_air + 237.3))
        ea = es * (rh / 100.0)
        return max(0.0, es - ea)

    def gamma_conductance(self, W):
        eps = 1e-4
        if W >= self.W_crit:
            return self.gamma_max
        elif W <= self.W_pmp:
            return 0.0
        else:
            denom = max(eps, self.W_crit - self.W_pmp)
            return self.gamma_max * (W - self.W_pmp) / denom

    def evapotranspiration(self, W, T_air, rh, is_crop=True):
        vpd = self.vpd_kpa(T_air, rh)
        eps = 1e-4
        if is_crop:
            gamma = self.gamma_conductance(W)
            transp = gamma * vpd
        else:
            transp = 0.0
            
        # Evaporación directa del suelo sombreado por biomasa/rastrojo
        evap_suelo = self.E_suelo_0 * (W / max(eps, self.W_cc)) * math.exp(-self.lambda_B * self.B)
        return transp + evap_suelo

    def step(self, W, P0, I_irr, T_air, rh, dt=1.0, is_crop=True):
        """
        Integración de EDO 2 en un paso temporal dt (días):
        dW/dt = P0*cos(theta) + eta_riego*I - ETc(T, W) - kd*sin(theta)*W
        con corte de saturación W_cc y runoff instantáneo.
        """
        ETc = self.evapotranspiration(W, T_air, rh, is_crop=is_crop)
        drainage = self.kd * self.sin_theta * W
        infil = P0 * self.cos_theta + self.eta_riego * I_irr
        
        dW_dt = infil - ETc - drainage
        W_next = W + dW_dt * dt
        
        runoff = 0.0
        if W_next > self.W_cc:
            runoff = W_next - self.W_cc
            W_next = self.W_cc
        elif W_next < 0.0:
            W_next = 0.0
            
        return W_next, ETc, drainage, runoff, dW_dt

print("Clase SoilHydrologyEDO2 definida exitosamente.")
