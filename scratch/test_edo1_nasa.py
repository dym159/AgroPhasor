import urllib.request
import json
import math

def fetch_nasa_hourly(lat=-12.06, lon=-75.21, start="20230101", end="20230102"):
    url = (
        f"https://power.larc.nasa.gov/api/temporal/hourly/point?"
        f"parameters=T2M,ALLSKY_SFC_SW_DWN,RH2M&community=AG&"
        f"longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON"
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'AgroPhasor-Test/1.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return data['properties']['parameter']

def run_test():
    params = fetch_nasa_hourly()
    t2m = params['T2M']
    rad = params['ALLSKY_SFC_SW_DWN']
    rh2m = params['RH2M']
    
    # Parametros fisiologicos de cultivo (ej. Papa / Maiz en Mantaro)
    Cp = 25000.0        # J / (m2 * C) -> masa termica foliar
    hc = 25.0           # W / (m2 * C) -> coeficiente convectivo (viento moderado)
    alpha = 0.8         # absortividad solar de vegetacion
    # Factor latente: transpiracion activa
    lambda_gamma_max = 85.0 # W / (m2 * kPa) -> refrigeracion transpiratoria tipica
    tau = Cp / hc       # 1000 segundos (~16.6 min)
    dt_sec = 3600.0     # 1 hora

    timestamps = sorted(t2m.keys())[:24] # Primeras 24 horas
    
    T_water = t2m[timestamps[0]]
    T_drought = t2m[timestamps[0]]
    
    print("=" * 95)
    print("SIMULACIÓN DE EDO 1 FORZADA CON DATOS REALES DE NASA POWER (VALLE DEL MANTARO)")
    print("=" * 95)
    print(f"{'Hora':<7} | {'T_aire':<8} | {'Rad (W/m2)':<12} | {'RH (%)':<7} | {'T_agua (°C)':<12} | {'T_sequía (°C)':<13} | {'ΔT Sequía-Agua':<16} | {'Diagnóstico':<12}")
    print("-" * 95)
    
    for ts in timestamps:
        Text = t2m[ts]
        frad_mj = rad[ts]
        frad = frad_mj * (1e6 / 3600.0) # Convertir MJ/hr a W/m2!
        rh = rh2m[ts]
        
        # Presion de vapor del aire (ea en kPa)
        es_air = 0.6108 * math.exp((17.27 * Text) / (Text + 237.3))
        ea = es_air * (rh / 100.0)
        
        # --- Caso Con Agua (gamma_c = 1.0) ---
        es_k_w = 0.6108 * math.exp((17.27 * T_water) / (T_water + 237.3))
        vpd_k_w = max(0.0, es_k_w - ea)
        T_eq_w = Text + (alpha * frad - lambda_gamma_max * 1.0 * vpd_k_w) / hc
        T_water = T_eq_w + (T_water - T_eq_w) * math.exp(-dt_sec / tau)
        
        # --- Caso Sequía (gamma_c = 0.0, estomas cerrados) ---
        T_eq_d = Text + (alpha * frad - 0.0) / hc
        T_drought = T_eq_d + (T_drought - T_eq_d) * math.exp(-dt_sec / tau)
        
        hour_str = ts[-2:] + ":00"
        diff = T_drought - T_water
        
        if frad > 50:
            if T_water <= Text + 1.0:
                diag = "Confort / Oasis"
            else:
                diag = "Cálido"
            if diff > 5.0:
                diag += " | FIEBRE"
        else:
            diag = "Noche / Equil"
            
        print(f"{hour_str:<7} | {Text:<8.1f} | {frad:<12.1f} | {rh:<7.1f} | {T_water:<12.1f} | {T_drought:<13.1f} | {diff:<+16.1f} | {diag:<12}")

run_test()
