/**
 * AgroPhasor - API & Resilience Client
 * Handles simulation requests, network errors, and offline fallback mode.
 */

import { CONFIG } from './config.js';

export class ApiService {
  constructor() {
    this.baseUrl = CONFIG.API.BASE_URL;
    this.isServerOnline = false;
    this.lastSimulationResult = null;
    this.forceFailureForTesting = false; // Enables UI resilience failure testing
  }

  /**
   * Check connectivity with the backend server
   */
  async checkHealth() {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);

      const response = await fetch(`${this.baseUrl}${CONFIG.API.HEALTH_ENDPOINT}`, {
        method: "GET",
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      this.isServerOnline = response.ok;
      return this.isServerOnline;
    } catch {
      this.isServerOnline = false;
      return false;
    }
  }

  /**
   * Send GeoJSON and parameters to the server to run the simulation.
   * If the simulation fails or the network is offline, THE LOT SELECTION IS PRESERVED.
   */
  async runSimulation(payload, options = {}) {
    // If the user enabled the test failure checkbox
    if (this.forceFailureForTesting) {
      await new Promise(r => setTimeout(r, 600));
      const error = new Error("Induced test error: The simulation server rejected the request (Simulation failed).");
      error.isSimulatedTest = true;
      error.retainedLoteId = payload.lote_seleccionado_id;
      throw error;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), CONFIG.API.TIMEOUT_MS);

      const response = await fetch(`${this.baseUrl}${CONFIG.API.SIMULATION_ENDPOINT}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: JSON.stringify(payload),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorBody = await response.text().catch(() => "");
        const error = new Error(`Server error (${response.status}): ${errorBody || response.statusText}`);
        error.status = response.status;
        error.retainedLoteId = payload.lote_seleccionado_id;
        throw error;
      }

      const result = await response.json();
      this.lastSimulationResult = result;
      this.isServerOnline = true;
      return result;

    } catch (networkError) {
      // Record that the backend did not respond
      this.isServerOnline = false;

      // If options allow offline fallback, return realistic synthetic data
      if (options.useOfflineFallback) {
        console.warn("API unreachable. Generating fallback contingency response (Local backup per CC-02)...", networkError);
        const fallbackResult = this.generateRealisticMockResponse(payload);
        this.lastSimulationResult = fallbackResult;
        fallbackResult._is_fallback = true;
        fallbackResult._original_error = networkError.message;
        return fallbackResult;
      }

      // Propagate the error while preserving selected lot information
      networkError.retainedLoteId = payload.lote_seleccionado_id;
      networkError.isNetworkError = true;
      throw networkError;
    }
  }

  async runParcelEdo1(lote, signal) {
    const response = await fetch(`${this.baseUrl}/api/v1/parcelas/edo1`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ geometry: lote.geometry, crop_id: lote.cultivo_asignado }),
      signal: AbortSignal.any([signal, AbortSignal.timeout(120000)])
    });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
      throw new Error(data?.error || 'The server could not compute canopy temperature.');
    }
    return data;
  }

  /**
   * Generate a synthetic fallback response aligned with Physics & Math parameters
   * (CC-02 Contract and Master Plan)
   */
  generateRealisticMockResponse(payload) {
    const loteId = payload.lote_seleccionado_id;
    const mode = payload.modo_prioridad || "balance_optimo";

    return {
      status: "success",
      meta: {
        engine: "AgroPhasor-ODE-Solver-v1.0 (Local Contingency Mode)",
        nasa_power_source: "POWER/AG Climatology (1991-2023)",
        timestamp: new Date().toISOString(),
        lote_id: loteId,
        elevation_m: 3250
      },
      // Physical indicators agreed per cell
      indicadores: {
        humedad_radicular_W: {
          valor: 142.5,
          unidad: "mm",
          estado: "Adequate",
          color: "#10b981",
          descripcion: "Root-zone moisture sufficient for tubers and legumes."
        },
        temperatura_dosel_T: {
          valor: 16.8,
          unidad: "°C",
          estado: "Optimal",
          color: "#3b82f6",
          descripcion: "No thermal stress and no immediate severe frost risk."
        },
        nutrientes_NPK: {
          N: { valor: 88, unidad: "kg/ha", nivel: "Medium" },
          P: { valor: 34, unidad: "kg/ha", nivel: "High" },
          K: { valor: 195, unidad: "kg/ha", nivel: "Optimal" },
          estado_general: "Fertile"
        },
        biomasa_aerea_B: {
          valor: 11.8,
          unidad: "t/ha",
          estado: "Vigorous growth"
        },
        espesor_fertil_H: {
          valor: 278,
          unidad: "mm",
          tasa_erosion: "0.28 mm/year (Low)",
          estado: "Protected"
        },
        escudo_ambiental: {
          indice: 87,
          max: 100,
          calificacion: "High Resilience",
          color: "#10b981"
        }
      },
      // Rotation comparator (Current plan vs Pareto suggestion)
      rotacion_recomendada: {
        plan_actual: [
          { periodo: "P1 (Jan-May)", cultivo: "Canchan Potato", familia: "Solanaceae", rendimiento_est: "13.2 t/ha" },
          { periodo: "P2 (Jun-Dec)", cultivo: "Canchan Potato (Monoculture)", familia: "Solanaceae", alerta: "Pest risk and K depletion" }
        ],
        sugerencia_optimizada: [
          { periodo: "P1 (Jan-May)", cultivo: "Canchan Potato", familia: "Solanaceae", rendimiento_est: "14.1 t/ha" },
          { periodo: "P2 (Jun-Dec)", cultivo: "Green Fava Beans", familia: "Fabaceae", ventaja: "Biological N fixation (+45 kg/ha) and pest cycle break" },
          { periodo: "P3 (Future)", cultivo: "Quinoa or Barley", familia: "Poaceae / Cover", ventaja: "Crop residue input and anti-erosion cover" }
        ],
        motivo_agronomico: "Rotating Potato with Green Fava Beans restores depleted nitrogen, suppresses nematodes, and saves up to 25% of chemical fertilizer on the next planting.",
        metricas_comparativas: {
          ahorro_agua_pct: 18,
          aumento_fertilidad_pct: 32,
          reduccion_riesgo_climatico_pct: 27,
          margen_economico_est: "+19.4%"
        }
      }
    };
  }
}
