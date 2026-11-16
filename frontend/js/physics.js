/**
 * AgroPhasor - Modelo Físico y Motor de Simulación What-If
 * Implementa:
 * 1. Balances físicos por celda (W, T, H, NPK, B)
 * 2. Tasa de erosión y hundimiento del suelo en función de pendiente (theta), lluvia (delta P) y rastrojo (r_res)
 * 3. Coloración edáfica (Marrón fértil <-> Gris rocoso degradado)
 * 4. Ley del Mínimo de Liebig para Salud Química (eta_nutrientes) y nutriente limitante
 * 5. Índice de Escudo Ambiental (Psi) y sus 4 estados (Azul Cobalto, Violeta/Ámbar, Rojo Intenso, Desactivado)
 * 6. Alertas de Riego (W_crit, tau_aviso, I_sugerido) y Confianza Montecarlo
 */

export class AgroPhysicsEngine {
  constructor() {
    // Parámetros base del Valle del Mantaro (Junín, 3250 msnm)
    this.BASELINE = {
      W_max: 200,      // Capacidad de campo (mm)
      W_base: 142.5,   // Humedad radicular inicial (mm)
      W_crit: 90.0,    // Humedad crítica de marchitez (mm)
      T_base: 16.5,    // Temp dosel base (°C)
      H_base: 280,     // Espesor fértil inicial (mm)
      N_opt: 150,      // Requerimiento óptimo Nitrógeno (kg/ha)
      P_opt: 80,       // Requerimiento óptimo Fósforo (kg/ha)
      K_opt: 220       // Requerimiento óptimo Potasio (kg/ha)
    };
  }

  /**
   * Ejecutar cálculo instantáneo a partir de las perillas de control
   */
  evaluate(controls) {
    const {
      deltaP0 = 0,         // Anomalía lluvia (%) [-50 a +50]
      deltaText = 0,       // Anomalía temperatura (°C) [-5 a +5]
      slopeTheta = 8,      // Pendiente en grados [0 a 35]
      irrigationI = 0,     // Riego aplicado (mm) [0 a 60]
      fertN = 90,          // Dosis Nitrógeno (kg/ha) [0 a 180]
      fertP = 35,          // Dosis Fósforo (kg/ha) [0 a 120]
      fertK = 180,         // Dosis Potasio (kg/ha) [0 a 240]
      rRes = 0.35,         // Fracción de rastrojo [0 a 1]
      stage = "cultivo"    // "cultivo" | "transicion"
    } = controls;

    // 1. BALANCE HÍDRICO (Humedad radicular W)
    // El rastrojo reduce la evaporación; deltaText la acelera
    const evapFactor = 1.0 + (deltaText * 0.05) - (rRes * 0.25);
    const rainDeltaMm = (deltaP0 / 100) * 35;
    let W = this.BASELINE.W_base + irrigationI + rainDeltaMm - (evapFactor * 8);
    W = Math.max(25, Math.min(this.BASELINE.W_max, W));

    // 2. TEMPERATURA DEL DOSEL T (°C)
    // El enfriamiento evaporativo depende de la humedad del suelo y rastrojo
    const cooling = (W / this.BASELINE.W_max) * 2.8 + (rRes * 1.2);
    const T = Number((this.BASELINE.T_base + deltaText - cooling).toFixed(1));

    // 3. SALUD QUÍMICA POR LEY DEL MÍNIMO DE LIEBIG (eta_nutrientes)
    const eta_N = Math.min(1.0, Math.max(0.1, fertN / this.BASELINE.N_opt));
    const eta_P = Math.min(1.0, Math.max(0.1, fertP / this.BASELINE.P_opt));
    const eta_K = Math.min(1.0, Math.max(0.1, fertK / this.BASELINE.K_opt));

    let limitingNutrient = "Nitrógeno (N)";
    let eta_nutrientes = eta_N;

    if (eta_P < eta_nutrientes) {
      eta_nutrientes = eta_P;
      limitingNutrient = "Fósforo (P)";
    }
    if (eta_K < eta_nutrientes) {
      eta_nutrientes = eta_K;
      limitingNutrient = "Potasio (K)";
    }

    eta_nutrientes = Number(eta_nutrientes.toFixed(3));

    // 4. VARIACIÓN DE ALTURA DEL TERRENO EN FUNCIÓN DE LA PRECIPITACIÓN Y PENDIENTE
    const slopeRad = (slopeTheta * Math.PI) / 180;
    const sinTheta = Math.sin(slopeRad);
    const rainEnergy = Math.max(0.2, 1.0 + (deltaP0 / 100));
    const betaSplash = 0.25;
    const rainTopographicFactor = betaSplash + (1.0 - betaSplash) * sinTheta;
    const residueCoverProtection = 1.0 - (rRes * 0.88);
    
    // Tasa anual de erosión/desgaste pluvial (mm/año) gobernada por la lluvia
    const erosionRateMmYear = Number((5.2 * rainEnergy * rainTopographicFactor * residueCoverProtection).toFixed(2));
    
    // Hundimiento físico para visualización 2.5D (mm perdidos por precipitaciones)
    const erosionSinkingMm = Math.min(65, erosionRateMmYear * 6.5);
    const currentH = Math.max(120, this.BASELINE.H_base - erosionSinkingMm);
    const retentionRatio = currentH / this.BASELINE.H_base;

    // Color de la tierra (Marrón fértil <-> Gris árido/degradado) dependiendo de nutrientes y humedad
    const waterSaturation = Math.max(0, Math.min(1, (W - 25) / (this.BASELINE.W_max - 25)));
    const soilVitalityIndex = Math.max(0, Math.min(1, retentionRatio * (0.55 * eta_nutrientes + 0.45 * waterSaturation)));
    const degradationFactor = Math.min(1.0, 1.0 - soilVitalityIndex);
    const soilColor = this.interpolateSoilColor(degradationFactor);

    // 5. BIOMASA AÉREA B (t/ha)
    let B = 0;
    if (stage === "cultivo") {
      const waterFactor = Math.min(1.0, W / 130);
      const tempFactor = Math.max(0.2, 1.0 - Math.abs(T - 16.5) * 0.08);
      B = Number((15.5 * eta_nutrientes * waterFactor * tempFactor).toFixed(1));
    }

    // 6. ÁREA DE LISSAJOUS Y ESCUDO AMBIENTAL (Psi: ROJO [área baja] <-> AZUL [área buena])
    let lissajousArea = 0;
    let eta_lissajous = 0;
    let Psi = 0;
    let shieldState = "desactivado";
    let shieldColor = "#64748b";
    let shieldName = "Escudo Desactivado (Transición)";

    if (stage === "transicion") {
      Psi = 0;
      shieldState = "desactivado";
      shieldColor = "rgba(100, 116, 139, 0.25)";
      shieldName = "Desactivado (Suelo desnudo)";
    } else {
      const waterResilience = Math.min(1.0, W / 140);
      const thermalResilience = Math.max(0.1, 1.0 - Math.max(0, (Math.abs(T - 16.5) - 2) * 0.12));
      // Área del ciclo de histéresis de Lissajous A_L (°C²) proporcional a la apertura estomática y confort
      lissajousArea = Number((32.0 * waterResilience * thermalResilience * (0.5 + 0.5 * eta_nutrientes)).toFixed(2));
      eta_lissajous = Number((lissajousArea / (lissajousArea + 18.0)).toFixed(3));

      const psiBio = waterResilience * thermalResilience * eta_nutrientes;
      Psi = Number((0.55 * eta_lissajous + 0.45 * psiBio).toFixed(2));

      // Color continuo ROJO (249,64,70) -> AZUL (42,155,255) según el área/nivel del escudo
      const rCol = Math.round(249 + (42 - 249) * Psi);
      const gCol = Math.round(64 + (155 - 64) * Psi);
      const bCol = Math.round(70 + (255 - 70) * Psi);
      shieldColor = `rgb(${rCol}, ${gCol}, ${bCol})`;

      if (Psi >= 0.70) {
        shieldState = "azul_cobalto";
        shieldName = "Azul Cobalto (Óptima Resiliencia)";
      } else if (Psi >= 0.38) {
        shieldState = "violeta_ambar";
        shieldName = "Violeta / Ámbar (Estrés Moderado)";
      } else {
        shieldState = "rojo_intenso";
        shieldName = "Rojo Intenso (Estrés Crítico)";
      }
    }

    // 7. ALERTAS DE RIEGO
    const W_crit = this.BASELINE.W_crit;
    const isWaterStressAlert = W <= (W_crit + 25);
    
    // Aviso anticipado (tau_aviso en días antes de llegar a W_crit)
    const dailyDepletionRate = Math.max(2.5, 4.0 * evapFactor);
    const daysUntilCrit = Math.max(0, Math.round((W - W_crit) / dailyDepletionRate));
    const tauAviso = isWaterStressAlert ? Math.min(14, daysUntilCrit) : daysUntilCrit;
    
    // Lámina de riego sugerida en mm
    const Isugerido = Math.max(0, Math.round(this.BASELINE.W_max - W));

    // 8. NIVEL DE CONFIANZA MONTECARLO (%) Y BRECHAS
    // Dispersión según extremos climáticos
    const climatePerturbationStress = (Math.abs(deltaP0) / 50) * 0.12 + (Math.abs(deltaText) / 5) * 0.14;
    const montecarloConfidence = Math.max(68, Math.round(96 - climatePerturbationStress * 100));

    return {
      // Estado de columnas 2.5D
      W: Number(W.toFixed(1)),
      T,
      H: Math.round(currentH),
      B,
      erosionRateMmYear,
      erosionSinkingMm: Number(erosionSinkingMm.toFixed(1)),
      degradationFactor: Number(degradationFactor.toFixed(2)),
      soilColor,

      // Salud química Liebig
      eta_nutrientes,
      eta_N: Number(eta_N.toFixed(2)),
      eta_P: Number(eta_P.toFixed(2)),
      eta_K: Number(eta_K.toFixed(2)),
      limitingNutrient,

      // Escudo ambiental y área de Lissajous
      lissajousArea,
      eta_lissajous,
      soilVitalityIndex: Number(soilVitalityIndex.toFixed(3)),
      Psi,
      shieldState, // "azul_cobalto" | "violeta_ambar" | "rojo_intenso" | "desactivado"
      shieldColor,
      shieldName,

      // Alertas de riego
      irrigationAlert: {
        active: isWaterStressAlert,
        W_crit,
        tauAviso,
        Isugerido
      },

      // Confianza Montecarlo y metadatos
      montecarloConfidence,
      dataGaps: {
        nasaPower: "Observado diario (1991-2023) - 0.5°",
        elevationSrtm: `SRTM 30m - Pendiente ${slopeTheta}°`,
        soilNPK: "Muestreo local calibrado",
        smapMoisture: "Desagregación empírica 9km -> celda"
      }
    };
  }

  /**
   * Interpolar color de tierra: Marrón fértil (#24160c) -> Gris rocoso (#52525b)
   */
  interpolateSoilColor(factor) {
    // Fértil: RGB (36, 44, 28) / (45, 28, 16)
    const fertile = { r: 38, g: 30, b: 20 };
    // Rocoso erosionado: RGB (100, 105, 115)
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
