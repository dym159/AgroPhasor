/**
 * AgroPhasor - Cliente de API y Resiliencia
 * Manejo de peticiones de simulación, errores de red y modo de respaldo offline.
 */

import { CONFIG } from './config.js';

export class ApiService {
  constructor() {
    this.baseUrl = CONFIG.API.BASE_URL;
    this.isServerOnline = false;
    this.lastSimulationResult = null;
    this.forceFailureForTesting = false; // Permite probar la resiliencia en la UI
  }

  /**
   * Verificar conectividad con el servidor backend
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
   * Enviar GeoJSON y parámetros al servidor para ejecutar la simulación
   * Si falla la simulación o no hay red, SE CONSERVA LA SELECCIÓN DEL LOTE.
   */
  async runSimulation(payload, options = {}) {
    // Si el usuario activó la casilla de prueba de error
    if (this.forceFailureForTesting) {
      await new Promise(r => setTimeout(r, 600));
      const error = new Error("Error inducido de prueba: El servidor de simulación rechazó la solicitud (Simulación fallida).");
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
        const error = new Error(`Error del servidor (${response.status}): ${errorBody || response.statusText}`);
        error.status = response.status;
        error.retainedLoteId = payload.lote_seleccionado_id;
        throw error;
      }

      const result = await response.json();
      this.lastSimulationResult = result;
      this.isServerOnline = true;
      return result;

    } catch (networkError) {
      // Registrar que el backend no respondió
      this.isServerOnline = false;

      // Si las opciones permiten usar respaldo offline, devolver datos sintéticos realistas
      if (options.useOfflineFallback) {
        console.warn("API inaccesible. Generando respuesta de contingencia (Respaldo local según CC-02)...", networkError);
        const fallbackResult = this.generateRealisticMockResponse(payload);
        this.lastSimulationResult = fallbackResult;
        fallbackResult._is_fallback = true;
        fallbackResult._original_error = networkError.message;
        return fallbackResult;
      }

      // Propagar el error preservando la información del lote seleccionado
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
      throw new Error(data?.error || 'El servidor no pudo calcular la temperatura del dosel.');
    }
    return data;
  }

  /**
   * Generar respuesta sintética basada en los parámetros acordados con Física y Matemática
   * (Contrato CC-02 y Plan Maestro)
   */
  generateRealisticMockResponse(payload) {
    const loteId = payload.lote_seleccionado_id;
    const mode = payload.modo_prioridad || "balance_optimo";

    return {
      status: "success",
      meta: {
        engine: "AgroPhasor-ODE-Solver-v1.0 (Modo Contingencia Local)",
        nasa_power_source: "POWER/AG Climatology (1991-2023)",
        timestamp: new Date().toISOString(),
        lote_id: loteId,
        elevation_m: 3250
      },
      // Indicadores físicos acordados por celda
      indicadores: {
        humedad_radicular_W: {
          valor: 142.5,
          unidad: "mm",
          estado: "Adecuado",
          color: "#10b981",
          descripcion: "Humedad en zona de raíces suficiente para tubérculos y leguminosas."
        },
        temperatura_dosel_T: {
          valor: 16.8,
          unidad: "°C",
          estado: "Óptimo",
          color: "#3b82f6",
          descripcion: "Sin estrés térmico ni riesgo inmediato de helada severa."
        },
        nutrientes_NPK: {
          N: { valor: 88, unidad: "kg/ha", nivel: "Medio" },
          P: { valor: 34, unidad: "kg/ha", nivel: "Alto" },
          K: { valor: 195, unidad: "kg/ha", nivel: "Óptimo" },
          estado_general: "Fértil"
        },
        biomasa_aerea_B: {
          valor: 11.8,
          unidad: "t/ha",
          estado: "Crecimiento vigoroso"
        },
        espesor_fertil_H: {
          valor: 278,
          unidad: "mm",
          tasa_erosion: "0.28 mm/año (Baja)",
          estado: "Protegido"
        },
        escudo_ambiental: {
          indice: 87,
          max: 100,
          calificacion: "Alta Resiliencia",
          color: "#10b981"
        }
      },
      // Comparador de rotaciones (Plan actual vs Sugerencia de Pareto)
      rotacion_recomendada: {
        plan_actual: [
          { periodo: "P1 (Ene-May)", cultivo: "Papa Canchán", familia: "Solanáceas", rendimiento_est: "13.2 t/ha" },
          { periodo: "P2 (Jun-Dic)", cultivo: "Papa Canchán (Monocultivo)", familia: "Solanáceas", alerta: "Riesgo de plagas y agotamiento de K" }
        ],
        sugerencia_optimizada: [
          { periodo: "P1 (Ene-May)", cultivo: "Papa Canchán", familia: "Solanáceas", rendimiento_est: "14.1 t/ha" },
          { periodo: "P2 (Jun-Dic)", cultivo: "Habas Verdes / Serranas", familia: "Leguminosas", ventaja: "Fijación biológica de N (+45 kg/ha) y corte de ciclo de plagas" },
          { periodo: "P3 (Futuro)", cultivo: "Quinua o Cebada", familia: "Gramíneas / Cobertura", ventaja: "Aporte de rastrojo y cobertura contra erosión" }
        ],
        motivo_agronomico: "La rotación de Papa con Habas Verdes restaura el nitrógeno agotado, previene la incidencia de nematodos y ahorra hasta 25% de fertilización química en la siguiente siembra.",
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
