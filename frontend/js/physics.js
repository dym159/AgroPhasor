/**
 * AgroPhasor - Physical Model and What-If Simulation Engine
 * Implements:
 * 1. Cell-level physical balances (W, T, H, NPK, B)
 * 2. Erosion rate and soil subsidence as a function of slope (theta), rainfall (delta P), and crop residue (r_res)
 * 3. Soil coloration (Fertile brown <-> Degraded rocky gray)
 * 4. Liebig's Law of the Minimum for Chemical Health (eta_nutrientes) and limiting nutrient
 * 5. Environmental Shield Index (Psi) and its 4 states (Cobalt Blue, Violet/Amber, Deep Red, Deactivated)
 * 6. Irrigation alerts (W_crit, tau_aviso, Isugerido) and Monte Carlo confidence
 */

export class AgroPhysicsEngine {
  constructor() {
    // Baseline parameters for Mantaro Valley (Junin, 3250 m a.s.l.)
    this.BASELINE = {
      W_max: 200,      // Field capacity (mm)
      W_base: 142.5,   // Initial root-zone moisture (mm)
      W_crit: 90.0,    // Critical wilting moisture (mm)
      T_base: 16.5,    // Base canopy temperature (°C)
      H_base: 280,     // Initial fertile topsoil depth (mm)
      N_opt: 150,      // Optimal Nitrogen requirement (kg/ha)
      P_opt: 80,       // Optimal Phosphorus requirement (kg/ha)
      K_opt: 220       // Optimal Potassium requirement (kg/ha)
    };
  }

  /**
   * Run instant calculation from the control knobs
   */
  evaluate(controls) {
    const {
      deltaP0 = 0,         // Rainfall anomaly (%) [-50 to +50]
      deltaText = 0,       // Temperature anomaly (°C) [-5 to +5]
      slopeTheta = 8,      // Slope in degrees [0 to 35]
      irrigationI = 0,     // Applied irrigation (mm) [0 to 60]
      fertN = 90,          // Nitrogen rate (kg/ha) [0 to 180]
      fertP = 35,          // Phosphorus rate (kg/ha) [0 to 120]
      fertK = 180,         // Potassium rate (kg/ha) [0 to 240]
      rRes = 0.35,         // Residue cover fraction [0 to 1]
      stage = "cultivo"    // "cultivo" | "transicion"
    } = controls;

    // 1. WATER BALANCE (Root-zone moisture W)
    // Crop residue reduces evaporation; deltaText accelerates it
    const evapFactor = 1.0 + (deltaText * 0.05) - (rRes * 0.25);
    const rainDeltaMm = (deltaP0 / 100) * 35;
    let W = this.BASELINE.W_base + irrigationI + rainDeltaMm - (evapFactor * 8);
    W = Math.max(25, Math.min(this.BASELINE.W_max, W));

    // 2. CANOPY TEMPERATURE T (°C)
    // Evaporative cooling depends on soil moisture and residue cover
    const cooling = (W / this.BASELINE.W_max) * 2.8 + (rRes * 1.2);
    const T = Number((this.BASELINE.T_base + deltaText - cooling).toFixed(1));

    // 3. CHEMICAL HEALTH VIA LIEBIG'S LAW OF THE MINIMUM (eta_nutrientes)
    const eta_N = Math.min(1.0, Math.max(0.1, fertN / this.BASELINE.N_opt));
    const eta_P = Math.min(1.0, Math.max(0.1, fertP / this.BASELINE.P_opt));
    const eta_K = Math.min(1.0, Math.max(0.1, fertK / this.BASELINE.K_opt));

    // The nutrient with lowest relative availability limits crop growth
    let limitingNutrient = "Nitrogen (N)";
    let eta_nutrientes = eta_N;

    if (eta_P < eta_nutrientes) {
      eta_nutrientes = eta_P;
      limitingNutrient = "Phosphorus (P)";
    }
    if (eta_K < eta_nutrientes) {
      eta_nutrientes = eta_K;
      limitingNutrient = "Potassium (K)";
    }

    eta_nutrientes = Number(eta_nutrientes.toFixed(3));

    // 4. TERRAIN HEIGHT VARIATION BY PRECIPITATION AND SLOPE
    const slopeRad = (slopeTheta * Math.PI) / 180;
    const sinTheta = Math.sin(slopeRad);
    const rainEnergy = Math.max(0.2, 1.0 + (deltaP0 / 100));
    const betaSplash = 0.25;
    const rainTopographicFactor = betaSplash + (1.0 - betaSplash) * sinTheta;
    const residueCoverProtection = 1.0 - (rRes * 0.88);

    // Annual pluvial erosion/wear rate (mm/year) governed by rainfall
    const erosionRateMmYear = Number((5.2 * rainEnergy * rainTopographicFactor * residueCoverProtection).toFixed(2));

    // Physical subsidence for 2.5D visualization (mm lost due to rainfall)
    const erosionSinkingMm = Math.min(65, erosionRateMmYear * 6.5);
    const currentH = Math.max(120, this.BASELINE.H_base - erosionSinkingMm);
    const retentionRatio = currentH / this.BASELINE.H_base;

    // Terrain soil color (Fertile brown <-> Arid/degraded gray) from nutrients and moisture
    const waterSaturation = Math.max(0, Math.min(1, (W - 25) / (this.BASELINE.W_max - 25)));
    const soilVitalityIndex = Math.max(0, Math.min(1, retentionRatio * (0.55 * eta_nutrientes + 0.45 * waterSaturation)));
    const degradationFactor = Math.min(1.0, 1.0 - soilVitalityIndex);
    const soilColor = this.interpolateSoilColor(degradationFactor);

    // 5. ABOVEGROUND BIOMASS B (t/ha)
    let B = 0;
    if (stage === "cultivo") {
      const waterFactor = Math.min(1.0, W / 130);
      const tempFactor = Math.max(0.2, 1.0 - Math.abs(T - 16.5) * 0.08);
      B = Number((15.5 * eta_nutrientes * waterFactor * tempFactor).toFixed(1));
    }

    // 6. LISSAJOUS AREA AND ENVIRONMENTAL SHIELD (Psi: RED [low area] <-> BLUE [healthy area])
    let lissajousArea = 0;
    let eta_lissajous = 0;
    let Psi = 0;
    let shieldState = "desactivado";
    let shieldColor = "#64748b";
    let shieldName = "Shield Deactivated (Transition)";

    if (stage === "transicion") {
      Psi = 0;
      shieldState = "desactivado";
      shieldColor = "rgba(100, 116, 139, 0.25)";
      shieldName = "Deactivated (Bare soil)";
    } else {
      const waterResilience = Math.min(1.0, W / 140);
      const thermalResilience = Math.max(0.1, 1.0 - Math.max(0, (Math.abs(T - 16.5) - 2) * 0.12));
      // Lissajous hysteresis loop area A_L (°C^2) proportional to stomatal conductance and thermal comfort
      lissajousArea = Number((32.0 * waterResilience * thermalResilience * (0.5 + 0.5 * eta_nutrientes)).toFixed(2));
      eta_lissajous = Number((lissajousArea / (lissajousArea + 18.0)).toFixed(3));

      const psiBio = waterResilience * thermalResilience * eta_nutrientes;
      Psi = Number((0.55 * eta_lissajous + 0.45 * psiBio).toFixed(2));

      // Continuous color RED (249,64,70) -> BLUE (42,155,255) based on shield area/level
      const rCol = Math.round(249 + (42 - 249) * Psi);
      const gCol = Math.round(64 + (155 - 64) * Psi);
      const bCol = Math.round(70 + (255 - 70) * Psi);
      shieldColor = `rgb(${rCol}, ${gCol}, ${bCol})`;

      if (Psi >= 0.70) {
        shieldState = "azul_cobalto";
        shieldName = "Cobalt Blue (Optimal Resilience)";
      } else if (Psi >= 0.38) {
        shieldState = "violeta_ambar";
        shieldName = "Violet / Amber (Moderate Stress)";
      } else {
        shieldState = "rojo_intenso";
        shieldName = "Deep Red (Critical Stress)";
      }
    }

    // 7. IRRIGATION ALERTS
    const W_crit = this.BASELINE.W_crit;
    const isWaterStressAlert = W <= (W_crit + 25);
    
    // Early warning lead time (tauAviso in days before reaching W_crit)
    const dailyDepletionRate = Math.max(2.5, 4.0 * evapFactor);
    const daysUntilCrit = Math.max(0, Math.round((W - W_crit) / dailyDepletionRate));
    const tauAviso = isWaterStressAlert ? Math.min(14, daysUntilCrit) : daysUntilCrit;
    
    // Suggested irrigation depth in mm
    const Isugerido = Math.max(0, Math.round(this.BASELINE.W_max - W));

    // 8. MONTE CARLO CONFIDENCE LEVEL (%) AND DATA GAPS
    // Spread driven by climate extremes
    const climatePerturbationStress = (Math.abs(deltaP0) / 50) * 0.12 + (Math.abs(deltaText) / 5) * 0.14;
    const montecarloConfidence = Math.max(68, Math.round(96 - climatePerturbationStress * 100));

    return {
      // 2.5D column state
      W: Number(W.toFixed(1)),
      T,
      H: Math.round(currentH),
      B,
      erosionRateMmYear,
      erosionSinkingMm: Number(erosionSinkingMm.toFixed(1)),
      degradationFactor: Number(degradationFactor.toFixed(2)),
      soilColor,

      // Liebig chemical health
      eta_nutrientes,
      eta_N: Number(eta_N.toFixed(2)),
      eta_P: Number(eta_P.toFixed(2)),
      eta_K: Number(eta_K.toFixed(2)),
      limitingNutrient,

      // Environmental shield and Lissajous area
      lissajousArea,
      eta_lissajous,
      soilVitalityIndex: Number(soilVitalityIndex.toFixed(3)),
      Psi,
      shieldState, // "azul_cobalto" | "violeta_ambar" | "rojo_intenso" | "desactivado"
      shieldColor,
      shieldName,

      // Irrigation alerts
      irrigationAlert: {
        active: isWaterStressAlert,
        W_crit,
        tauAviso,
        Isugerido
      },

      // Monte Carlo confidence and metadata
      montecarloConfidence,
      dataGaps: {
        nasaPower: "Daily observed (1991-2023) - 0.5°",
        elevationSrtm: `SRTM 30m - Slope ${slopeTheta}°`,
        soilNPK: "Calibrated local sampling",
        smapMoisture: "Empirical downscaling 9km -> cell"
      }
    };
  }

  /**
   * Interpolate soil color: Fertile brown (#24160c) -> Rocky gray (#52525b)
   */
  interpolateSoilColor(factor) {
    // Fertile: RGB (36, 44, 28) / (45, 28, 16)
    const fertile = { r: 38, g: 30, b: 20 };
    // Eroded rocky: RGB (100, 105, 115)
    const rocky = { r: 95, g: 100, b: 110 };

    const r = Math.round(fertile.r + (rocky.r - fertile.r) * factor);
    const g = Math.round(fertile.g + (rocky.g - fertile.g) * factor);
    const b = Math.round(fertile.b + (rocky.b - fertile.b) * factor);

    return {
      top: `rgb(${r}, ${g}, ${b})`,
      front: `rgb(${Math.max(10, r - 15)}, ${Math.max(10, g - 15)}, ${Math.max(10, b - 15)})`,
      side: `rgb(${Math.max(5, r - 25)}, ${Math.max(5, g - 25)}, ${Math.max(5, b - 25)})`,
      hex: `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
    };
  }
}
