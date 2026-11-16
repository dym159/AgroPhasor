"""
AgroPhasor - ODE 3 Agro-Physical Engine: Vector Macronutrient Dynamics
=====================================================================
Step-wise linear matrix differential equation (Agrophasor.pdf, Sec 3.2.3):
    d N_i,j / dt = S_N,i,j(t) - Lambda_N,i,j(t) * N_i,j(t)

Where N_i,j(t) = [N_i,j(t), P_i,j(t), K_i,j(t)]^T in R^3_+ (kg/ha).

Multi-Sensor & Satellite Calibration:
  - NASA POWER & PRISM: Air temp T2M -> Tsoil(t) (microbial Q10) and solar radiation.
  - SMAP & GPM/IMERG: Root-zone soil moisture W_i,j(t) and rainfall P0(t).
  - SRTM (z_i,j, theta_i,j): Surface soil loss dH/dt and erosive drag of phosphorus and topsoil.
  - USDA NRCS SSURGO / WSS / FAO GAEZ: Organic matter OM_i,j (%), CEC (CIC_i,j cmolc/kg),
    soil pH_i,j and salinity EC_i,j (dS/m) defining the chemical modulator phi_pH,EC.
  - USDA CDL (CropScape) & Ag Data Commons: Rotation q(t), fixation Ffix, and uptake ka.
  - ECOSTRESS & Sentinel-2/Landsat: Spectral 'hunger vs. thirst' diagnostic and biomass vigor B(t).

Exact unconditionally non-negative analytical solution:
    N_i,j(t + dt) = exp(-Lambda * dt) * N_i,j(t) + dt * phi1(Lambda * dt) * S
    with phi1(z) = (1 - exp(-z)) / z
"""

import math
import numpy as np

def phi1(z):
    """
    Auxiliary matrix function phi1(z) = (1 - exp(-z)) / z
    Singularity-free as z -> 0 (Agrophasor.pdf, Sec 3.2.3).
    """
    z = np.asarray(z, dtype=np.float64)
    res = np.empty_like(z)
    small = np.abs(z) < 1e-6
    res[small] = 1.0 - 0.5 * z[small] + (z[small]**2) / 6.0
    res[~small] = (1.0 - np.exp(-z[~small])) / z[~small]
    return res

class AgroPhasorEDO3:
    def __init__(self,
                 # Edaphic parameters from SSURGO / WSS / STATSGO2
                 OM=3.5,            # Soil organic matter (%)
                 CIC=22.0,          # Cation Exchange Capacity (cmolc/kg)
                 pH=6.8,            # Topsoil pH (optimal 6.0 - 7.2)
                 EC=0.8,            # Electrical conductivity (dS/m - salinity)
                 Wcc=120.0,         # Soil field capacity (mm)
                 # Kinetic parameters for mineralization and leaching
                 k_min0=0.35,       # Basal N mineralization per %OM (kg N/(ha*day*%OM))
                 k_minP=0.04,       # Basal native P mineralization/desorption (kg P/(ha*day))
                 k_minK=0.65,       # Basal mineral K release from clays/feldspars (kg K/(ha*day))
                 k_lN=0.0020,       # Moisture- and 1/CEC-dependent N leaching rate
                 k_lK=0.0016,       # Moisture- and 1/CEC-dependent K leaching rate
                 # Surface water erosion drag coefficients (SRTM topography)
                 xi_N=0.04,         # Surface N loss per mm of eroded soil (1/mm)
                 xi_P=0.08,         # Surface P loss per mm of eroded soil (1/mm)
                 xi_K=0.03,         # Surface K loss per mm of eroded soil (1/mm)
                 # Liebig half-saturation constants (Agrophasor.pdf Sec 1.2 & 3.3)
                 KN=45.0,           # Nitrogen half-saturation constant (kg/ha)
                 KP=15.0,           # Phosphorus half-saturation constant (kg/ha)
                 KK=45.0,           # Potassium half-saturation constant (kg/ha)
                 # Temperature microbial kinetics
                 Q10=2.0,           # Microbial Q10 thermal response coefficient
                 # Stover recycling (Agrophasor.pdf Sec 3.3)
                 beta_K=16.0,       # Crop residue K content (kg K / t stover)
                 k_dec=0.025):      # Stover decomposition rate (1/day)
        
        self.OM = OM
        self.CIC = max(1.0, CIC)
        self.pH = pH
        self.EC = EC
        self.Wcc = Wcc
        
        self.k_min0 = k_min0
        self.k_minP = k_minP
        self.k_minK = k_minK
        self.k_lN = k_lN
        self.k_lK = k_lK
        
        self.xi_N = xi_N
        self.xi_P = xi_P
        self.xi_K = xi_K
        
        self.KN = KN
        self.KP = KP
        self.KK = KK
        
        self.Q10 = Q10
        self.beta_K = beta_K
        self.k_dec = k_dec
        
        # Basal chemical availability modulator phi_pH,EC in [0, 1]
        self.phi_pH_EC = self._calc_phi_pH_EC(self.pH, self.EC)

    def _calc_phi_pH_EC(self, pH, EC):
        """
        Chemical availability modulator phi_pH,EC in [0, 1] (Agrophasor.pdf Sec 1.3 & 2.4).
        - In acidic (pH < 5.5) or strongly alkaline (pH > 8.0) soils, nutrient availability drops.
        - Salinity (EC > 1.5 dS/m) penalizes root ionic transport.
        """
        if 6.0 <= pH <= 7.5:
            f_pH = 1.0
        elif pH < 6.0:
            f_pH = max(0.2, 1.0 - 0.25 * (6.0 - pH)**1.5)
        else:
            f_pH = max(0.3, 1.0 - 0.20 * (pH - 7.5)**1.5)
            
        if EC <= 1.5:
            f_EC = 1.0
        else:
            f_EC = max(0.1, 1.0 - 0.15 * (EC - 1.5))
            
        return float(np.clip(f_pH * f_EC, 0.0, 1.0))

    def f_T(self, T_soil):
        """Q10 enzymatic and microbial kinetics centered at 20 °C (Agrophasor.pdf Sec 3.3)"""
        return float(self.Q10 ** ((T_soil - 20.0) / 10.0))

    def liebig_factor(self, N_vec):
        """
        Liebig's Law of the Minimum (Agrophasor.pdf, Sec. 1.2 and 3.3):
        eta_N = min( N/(N + KN), P/(P + KP), K/(K + KK) ) in [0, 1]
        """
        n, p, k = max(0.0, N_vec[0]), max(0.0, N_vec[1]), max(0.0, N_vec[2])
        e_N = n / (n + self.KN)
        e_P = p / (p + self.KP)
        e_K = k / (k + self.KK)
        return min(e_N, e_P, e_K), (e_N, e_P, e_K)

    def step(self, N_vec, W, T_soil, erosion_rate, B=2.0,
             is_crop=True,
             # Crop-specific physiological parameters ck (USDA Ag Data Commons / CDL / FAO GAEZ)
             F_fix=0.0,       # Symbiotic N fixation (kg/(t biomass * day)) -> legumes > 0
             F_sol=0.0,       # Root P solubilization (kg/(t biomass * day))
             ka_N=0.00010,    # Root N uptake coefficient (1/(mm*day))
             ka_P=0.00008,    # Root P uptake coefficient (1/(mm*day))
             ka_K=0.00008,    # Root K uptake coefficient (1/(mm*day))
             # Control inputs (synthetic fertilization kg/(ha*day))
             F_fert=np.array([0.0, 0.0, 0.0]),
             dt=1.0):
        """
        Advances the state vector N_i,j(t) = [N, P, K]^T by one step dt (days)
        according to the exact equations in Agrophasor.pdf (Sec. 3.2.3).
        """
        N_curr = np.array(N_vec, dtype=np.float64)
        fT = self.f_T(T_soil)
        Ic = 1.0 if is_crop else 0.0
        
        # Relative moisture W / Wcc
        w_rel = np.clip(W / max(1.0, self.Wcc), 0.0, 1.2)
        
        # Surface erosion rate |dH/dt| (mm/day)
        eros = max(0.0, erosion_rate)

        # ----------------- SOURCE VECTOR S_N(t) -----------------
        # 1. Nitrogen (Agrophasor.pdf Sec 3.2.3a):
        # SN = FN,fert + Ffix,c * B + kmin,0 * OM * (W/Wcc) * fT
        SN_min = self.k_min0 * self.OM * w_rel * fT
        SN_fix = (F_fix * B) if is_crop else 0.0
        SN = F_fert[0] + SN_fix + SN_min
        
        # 2. Phosphorus (Agrophasor.pdf Sec 3.2.3b):
        # SP = FP,fert + Fsol,c * B + kmin,P * (W/Wcc) * fT
        SP_sol = (F_sol * B) if is_crop else 0.0
        SP_min = self.k_minP * w_rel * fT
        SP = F_fert[1] + SP_sol + SP_min
        
        # 3. Potassium (Agrophasor.pdf Sec 3.2.3c):
        # SK = FK,fert + SK,res(q, B) + kmin,K * fT
        # SK,res = I(q = Transition) * beta_K * k_dec * B
        SK_res = ((1.0 - Ic) * self.beta_K * self.k_dec * B)
        SK_min = self.k_minK * fT
        SK = F_fert[2] + SK_res + SK_min
        
        S_vec = np.array([SN, SP, SK], dtype=np.float64)

        # ----------------- LOSS RATE VECTOR Lambda_N(t) -----------------
        # 1. Nitrogen:
        # Lambda_N = W * (kl,N / CIC + Ic * phi_pH,EC * ka,N * fT) + xi_N * eros
        Lambda_N = W * ((self.k_lN / self.CIC) + Ic * self.phi_pH_EC * ka_N * fT) + self.xi_N * eros
        
        # 2. Phosphorus (immune to vertical leaching; transport via root diffusion + erosive entrainment):
        # Lambda_P = Ic * phi_pH,EC * ka,P * fT * W + xi_P * eros
        Lambda_P = Ic * self.phi_pH_EC * ka_P * fT * W + self.xi_P * eros
        
        # 3. Potassium (electrostatically retained by CEC):
        # Lambda_K = W * (kl,K / CIC + Ic * phi_pH,EC * ka_K * fT) + xi_K * eros
        Lambda_K = W * ((self.k_lK / self.CIC) + Ic * self.phi_pH_EC * ka_K * fT) + self.xi_K * eros
        
        Lambda_vec = np.array([Lambda_N, Lambda_P, Lambda_K], dtype=np.float64)

        # ----------------- EXACT ANALYTICAL INTEGRATION -----------------
        # N(t + dt) = exp(-Lambda * dt) * N(t) + dt * phi1(Lambda * dt) * S
        z = Lambda_vec * dt
        decay = np.exp(-z)
        phi_val = phi1(z)
        
        N_next = decay * N_curr + dt * phi_val * S_vec
        
        # Unconditional non-negativity guarantee (Biogeochemical Boundary, Sec. 1.3)
        N_next = np.maximum(N_next, 0.0)
        
        diagnostics = {
            'S_vec': S_vec,
            'Lambda_vec': Lambda_vec,
            'SN_min': SN_min,
            'SN_fix': SN_fix,
            'SK_res': SK_res,
            'leach_N': (self.k_lN / self.CIC) * W * N_curr[0],
            'leach_K': (self.k_lK / self.CIC) * W * N_curr[2],
            'uptake_N': Ic * self.phi_pH_EC * ka_N * fT * W * N_curr[0],
            'uptake_P': Ic * self.phi_pH_EC * ka_P * fT * W * N_curr[1],
            'uptake_K': Ic * self.phi_pH_EC * ka_K * fT * W * N_curr[2],
            'eros_P': self.xi_P * eros * N_curr[1]
        }
        
        return N_next, diagnostics

print("AgroPhasorEDO3 module compiled successfully.")
