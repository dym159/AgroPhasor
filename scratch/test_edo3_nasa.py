"""
AgroPhasor - Motor Agrofísico EDO 3: Dinámica Vectorial de Macronutrientes
========================================================================
Ecuación diferencial matricial lineal por paso temporal (Agrophasor.pdf, Sec 3.2.3):
    d N_i,j / dt = S_N,i,j(t) - Lambda_N,i,j(t) * N_i,j(t)

Donde N_i,j(t) = [N_i,j(t), P_i,j(t), K_i,j(t)]^T in R^3_+ (kg/ha).

Calibración Multisensor y Satelital:
  - NASA POWER & PRISM: Temperatura T2M -> Tsoil(t) (Q10 microbiano) y radiación solar.
  - SMAP & GPM/IMERG: Humedad radicular W_i,j(t) y precipitación P0(t).
  - SRTM (zi,j, theta_i,j): Desgaste superficial dH/dt y arrastre erosivo de fósforo y suelo.
  - USDA NRCS SSURGO / WSS / FAO GAEZ: Materia orgánica OM_i,j (%), CIC_i,j (cmolc/kg),
    pH_i,j y salinidad EC_i,j (dS/m) que definen el modulador químico phi_pH,EC.
  - USDA CDL (CropScape) & Ag Data Commons: Rotación q(t), fijación Ffix y absorción ka.
  - ECOSTRESS & Sentinel-2/Landsat: Diagnóstico espectral 'hambre vs. sed' y vigor de biomasa B(t).

Solución analítica exacta e incondicionalmente no negativa:
    N_i,j(t + dt) = exp(-Lambda * dt) * N_i,j(t) + dt * phi1(Lambda * dt) * S
    con phi1(z) = (1 - exp(-z)) / z
"""

import math
import numpy as np

def phi1(z):
    """
    Función auxiliar matricial phi1(z) = (1 - exp(-z)) / z
    Libre de singularidades para z -> 0 (Agrophasor.pdf, Sec 3.2.3).
    """
    z = np.asarray(z, dtype=np.float64)
    res = np.empty_like(z)
    small = np.abs(z) < 1e-6
    res[small] = 1.0 - 0.5 * z[small] + (z[small]**2) / 6.0
    res[~small] = (1.0 - np.exp(-z[~small])) / z[~small]
    return res

class AgroPhasorEDO3:
    def __init__(self,
                 # Parámetros edáficos de SSURGO / WSS / STATSGO2
                 OM=3.5,            # Materia orgánica del suelo (%)
                 CIC=22.0,          # Capacidad de Intercambio Catiónico (cmolc/kg)
                 pH=6.8,            # pH superficial del suelo (óptimo 6.0 - 7.2)
                 EC=0.8,            # Conductividad eléctrica (dS/m - salinidad)
                 Wcc=120.0,         # Capacidad de campo del suelo (mm)
                 # Parámetros cinéticos edáficos de mineralización y lixiviación
                 k_min0=0.35,       # Mineralización basal de N por OM (kg N/(ha*día*%OM))
                 k_minP=0.04,       # Mineralización basal / desorción de P nativo (kg P/(ha*día))
                 k_minK=0.65,       # Liberación basal de K mineral de arcillas/feldespatos (kg K/(ha*día))
                 k_lN=0.0020,       # Tasa de lixiviación de N dependiente de humedad y 1/CIC
                 k_lK=0.0016,       # Tasa de lixiviación de K dependiente de humedad y 1/CIC
                 # Coeficientes de arrastre por erosión hídrica superficial (topografía SRTM)
                 xi_N=0.04,         # Pérdida de N superficial por erosión (1/mm de suelo perdido)
                 xi_P=0.08,         # Pérdida de P superficial por erosión (1/mm de suelo perdido)
                 xi_K=0.03,         # Pérdida de K superficial por erosión (1/mm de suelo perdido)
                 # Parámetros de saturación de Liebig (Agrophasor.pdf Sec 1.2 y 3.3)
                 KN=45.0,           # Constante media de saturación de N (kg/ha)
                 KP=15.0,           # Constante media de saturación de P (kg/ha)
                 KK=45.0,           # Constante media de saturación de K (kg/ha)
                 # Cinética microbiana de temperatura
                 Q10=2.0,           # Coeficiente Q10 de respuesta térmica microbiana
                 # Reciclaje de rastrojo (Agrophasor.pdf Sec 3.3)
                 beta_K=16.0,       # Contenido de K en rastrojos (kg K / t rastrojo)
                 k_dec=0.025):      # Tasa de descomposición del rastrojo (1/día)
        
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
        
        # Modulador químico basal phi_pH,EC in [0, 1]
        self.phi_pH_EC = self._calc_phi_pH_EC(self.pH, self.EC)

    def _calc_phi_pH_EC(self, pH, EC):
        """
        Modulador de disponibilidad química phi_pH,EC in [0, 1] (Agrophasor.pdf Sec 1.3 y 2.4).
        - En suelos ácidos (pH < 5.5) o muy alcalinos (pH > 8.0) la disponibilidad de nutrientes decae.
        - Salinidad (EC > 1.5 dS/m) penaliza el transporte iónico radicular.
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
        """Cinética enzimática y microbiana Q10 centrada en 20 °C (Agrophasor.pdf Sec 3.3)"""
        return float(self.Q10 ** ((T_soil - 20.0) / 10.0))

    def liebig_factor(self, N_vec):
        """
        Ley del Mínimo de Liebig (Agrophasor.pdf, Sec. 1.2 y 3.3):
        eta_N = min( N/(N + KN), P/(P + KP), K/(K + KK) ) in [0, 1]
        """
        n, p, k = max(0.0, N_vec[0]), max(0.0, N_vec[1]), max(0.0, N_vec[2])
        e_N = n / (n + self.KN)
        e_P = p / (p + self.KP)
        e_K = k / (k + self.KK)
        return min(e_N, e_P, e_K), (e_N, e_P, e_K)

    def step(self, N_vec, W, T_soil, erosion_rate, B=2.0,
             is_crop=True,
             # Parámetros fisiológicos del cultivo específico ck (USDA Ag Data Commons / CDL / FAO GAEZ)
             F_fix=0.0,       # Fijación simbiótica de N (kg/(t biomasa * día)) -> leguminosas > 0
             F_sol=0.0,       # Solubilización radicular de P (kg/(t biomasa * día))
             ka_N=0.00010,    # Coeficiente de absorción radicular de N (1/(mm*día))
             ka_P=0.00008,    # Coeficiente de absorción radicular de P (1/(mm*día))
             ka_K=0.00008,    # Coeficiente de absorción radicular de K (1/(mm*día))
             # Entradas de control (fertilización artificial kg/(ha*día))
             F_fert=np.array([0.0, 0.0, 0.0]),
             dt=1.0):
        """
        Avanza el estado vectorial N_i,j(t) = [N, P, K]^T en un paso dt (días)
        según las ecuaciones exactas de Agrophasor.pdf (Sec. 3.2.3).
        """
        N_curr = np.array(N_vec, dtype=np.float64)
        fT = self.f_T(T_soil)
        Ic = 1.0 if is_crop else 0.0
        
        # Humedad relativa W / Wcc
        w_rel = np.clip(W / max(1.0, self.Wcc), 0.0, 1.2)
        
        # Tasa de erosión superficial |dH/dt| (mm/día)
        eros = max(0.0, erosion_rate)

        # ----------------- VECTOR DE FUENTES S_N(t) -----------------
        # 1. Nitrógeno (Agrophasor.pdf Sec 3.2.3a):
        # SN = FN,fert + Ffix,c * B + kmin,0 * OM * (W/Wcc) * fT
        SN_min = self.k_min0 * self.OM * w_rel * fT
        SN_fix = (F_fix * B) if is_crop else 0.0
        SN = F_fert[0] + SN_fix + SN_min
        
        # 2. Fósforo (Agrophasor.pdf Sec 3.2.3b):
        # SP = FP,fert + Fsol,c * B + kmin,P * (W/Wcc) * fT
        SP_sol = (F_sol * B) if is_crop else 0.0
        SP_min = self.k_minP * w_rel * fT
        SP = F_fert[1] + SP_sol + SP_min
        
        # 3. Potasio (Agrophasor.pdf Sec 3.2.3c):
        # SK = FK,fert + SK,res(q, B) + kmin,K * fT
        # SK,res = I(q = Transición) * beta_K * k_dec * B
        SK_res = ((1.0 - Ic) * self.beta_K * self.k_dec * B)
        SK_min = self.k_minK * fT
        SK = F_fert[2] + SK_res + SK_min
        
        S_vec = np.array([SN, SP, SK], dtype=np.float64)

        # ----------------- VECTOR DE TASAS DE PÉRDIDA Lambda_N(t) -----------------
        # 1. Nitrógeno:
        # Lambda_N = W * (kl,N / CIC + Ic * phi_pH,EC * ka,N * fT) + xi_N * eros
        Lambda_N = W * ((self.k_lN / self.CIC) + Ic * self.phi_pH_EC * ka_N * fT) + self.xi_N * eros
        
        # 2. Fósforo (inmune a lixiviación vertical; transporte por difusión radicular + arrastre erosivo):
        # Lambda_P = Ic * phi_pH,EC * ka,P * fT * W + xi_P * eros
        Lambda_P = Ic * self.phi_pH_EC * ka_P * fT * W + self.xi_P * eros
        
        # 3. Potasio (retenido electrostáticamente por CIC):
        # Lambda_K = W * (kl,K / CIC + Ic * phi_pH,EC * ka_K * fT) + xi_K * eros
        Lambda_K = W * ((self.k_lK / self.CIC) + Ic * self.phi_pH_EC * ka_K * fT) + self.xi_K * eros
        
        Lambda_vec = np.array([Lambda_N, Lambda_P, Lambda_K], dtype=np.float64)

        # ----------------- INTEGRACIÓN ANALÍTICA EXACTA -----------------
        # N(t + dt) = exp(-Lambda * dt) * N(t) + dt * phi1(Lambda * dt) * S
        z = Lambda_vec * dt
        decay = np.exp(-z)
        phi_val = phi1(z)
        
        N_next = decay * N_curr + dt * phi_val * S_vec
        
        # Garantía incondicional no-negativa (Frontera Biogeoquímica, Sec. 1.3)
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

print("Módulo AgroPhasorEDO3 compilado exitosamente.")
