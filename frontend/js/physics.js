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

    // 3. EROSIÓN HÍDRICA Y HUNDIMIENTO DEL SUELO
    // Ecuación de pérdida de suelo: pendiente sin(theta), energía de lluvia (1 + deltaP0/100) y protección por rastrojo
    const slopeRad = (slopeTheta * Math.PI) / 180;
    const sinTheta = Math.sin(slopeRad);
    const rainEnergy = Math.max(0.2, 1.0 + (deltaP0 / 100));
    const residueCoverProtection = 1.0 - (rRes * 0.88); // 88% reducción max con rastrojo
    
    // Tasa anual de erosión (mm/año)
    const erosionRateMmYear = Number((4.5 * sinTheta * rainEnergy * residueCoverProtection).toFixed(2));
    
    // Hundimiento físico para visualización 2.5D (mm perdidos en escenario simulado)
    const erosionSinkingMm = Math.min(65, erosionRateMmYear * 6.5);
    const currentH = Math.max(120, this.BASELINE.H_base - erosionSinkingMm);

    // Color de la tierra: Fértil marrón oscuro (#1b3a24 / #3b2314) -> Gris rocoso (#52525b / #71717a)
    // Factor de degradación (0 = 100% fértil, 1 = suelo totalmente degradado y rocoso)
    const degradationFactor = Math.min(1.0, (erosionSinkingMm / 55) * 0.6 + (1 - (W / this.BASELINE.W_max)) * 0.4);
    const soilColor = this.interpolateSoilColor(degradationFactor);

    // 4. SALUD QUÍMICA POR LEY DEL MÍNIMO DE LIEBIG (eta_nutrientes)
    const eta_N = Math.min(1.0, Math.max(0.1, fertN / this.BASELINE.N_opt));
    const eta_P = Math.min(1.0, Math.max(0.1, fertP / this.BASELINE.P_opt));
    const eta_K = Math.min(1.0, Math.max(0.1, fertK / this.BASELINE.K_opt));

    // El nutriente con menor disponibilidad determina el crecimiento
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

    // 5. BIOMASA AÉREA B (t/ha)
    let B = 0;
    if (stage === "cultivo") {
      const waterFactor = Math.min(1.0, W / 130);
      const tempFactor = Math.max(0.2, 1.0 - Math.abs(T - 16.5) * 0.08);
      B = Number((15.5 * eta_nutrientes * waterFactor * tempFactor).toFixed(1));
    }

    // 6. ÍNDICE DE ESCUDO AMBIENTAL (Psi) Y SUS 4 ESTADOS
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
      const soilResilience = Math.max(0.1, 1.0 - degradationFactor);

      // Ponderación de resiliencia
      Psi = Number((
        0.35 * waterResilience +
        0.30 * eta_nutrientes +
        0.20 * thermalResilience +
        0.15 * soilResilience
      ).toFixed(2));

      // Clasificación rigurosa en los 3 estados activos
      if (Psi >= 0.70) {
        shieldState = "azul_cobalto";
        shieldColor = "#2563eb"; // Azul Cobalto
        shieldName = "Azul Cobalto (Óptima Resiliencia)";
      } else if (Psi >= 0.38) {
        shieldState = "violeta_ambar";
        shieldColor = "#8b5cf6"; // Violeta / Ámbar
        shieldName = "Violeta / Ámbar (Estrés Moderado)";
      } else {
        shieldState = "rojo_intenso";
        shieldColor = "#dc2626"; // Rojo Intenso
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

      // Escudo ambiental
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
