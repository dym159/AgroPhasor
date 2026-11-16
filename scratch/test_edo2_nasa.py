import urllib.request
import json
import math
import numpy as np

def fetch_nasa_data(lat=-12.06, lon=-75.21, start="20230101", end="20230131"):
    """
    Fetch daily time series from NASA POWER:
    - PRECTOTCORR: Bias-corrected precipitation (mm/day)
    - T2M: Mean air temperature at 2 m (°C)
    - RH2M: Relative humidity at 2 m (%)
    - ALLSKY_SFC_SW_DWN: Incident solar radiation (MJ/m2/day)
    - GWETROOT: Root-zone soil wetness (0-1), MERRA-2/SMAP model
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
                 theta_fc=0.32,      # Field capacity (m3/m3 - Clay loam from SSURGO/WSS)
                 theta_wp=0.15,      # Permanent wilting point (m3/m3)
                 H_soil=400.0,       # Effective root depth Zr / soil thickness (mm)
                 slope_deg=10.0,     # SRTM slope (degrees)
                 p_c=0.50,           # Allowable depletion fraction (FAO 56)
                 gamma_max=1.8,      # Stomatal conductance / max transpiration factor (mm/(kPa*day))
                 E_suelo_0=2.0,      # Bare soil basal evaporation (mm/day)
                 lambda_B=0.4,       # Radiation extinction by leaf biomass
                 B=3.5,              # Aboveground biomass (t/ha)
                 kd=0.04,            # Slope-dependent gravitational drainage coefficient
                 eta_riego=0.85):    # Drip/sprinkler irrigation efficiency
        
        self.H_soil = H_soil
        self.theta_fc = theta_fc
        self.theta_wp = theta_wp
        self.W_cc = theta_fc * H_soil   # e.g., 0.32 * 400 = 128 mm
        self.W_pmp = theta_wp * H_soil  # e.g., 0.15 * 400 = 60 mm
        self.p_c = p_c
        # Critical water stress threshold (Wcrit)
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
        # Tetens formula
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
            
        # Direct soil evaporation shaded by canopy biomass / residue
        evap_suelo = self.E_suelo_0 * (W / max(eps, self.W_cc)) * math.exp(-self.lambda_B * self.B)
        return transp + evap_suelo

    def step(self, W, P0, I_irr, T_air, rh, dt=1.0, is_crop=True):
        """
        ODE 2 integration over time step dt (days):
        dW/dt = P0*cos(theta) + eta_riego*I - ETc(T, W) - kd*sin(theta)*W
        with saturation cutoff W_cc and instant surface runoff.
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

print("SoilHydrologyEDO2 class defined successfully.")
