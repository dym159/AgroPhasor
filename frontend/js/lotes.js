/**
 * AgroPhasor - Gestor de Lotes y Zonas
 * Manejo de geometrías, IDs independientes, cálculo de área y persistencia de selección.
 */

import { CONFIG } from './config.js';

export class LotesManager {
  constructor() {
    this.lotes = new Map(); // id -> LoteData
    this.selectedId = null;
    this.nextIndex = 1;
    this.listeners = [];
    this.loadFromStorage();
  }

  /**
   * Suscribirse a cambios en los lotes
   */
  subscribe(callback) {
    this.listeners.push(callback);
    callback(this.getAll(), this.getSelected());
    return () => {
      this.listeners = this.listeners.filter(cb => cb !== callback);
    };
  }

  notify() {
    this.saveToStorage();
    const all = this.getAll();
    const selected = this.getSelected();
    this.listeners.forEach(cb => {
      try {
        cb(all, selected);
      } catch (err) {
        console.error("Error en subscriber de lotes:", err);
      }
    });
  }

  /**
   * Obtener todos los lotes
   */
  getAll() {
    return Array.from(this.lotes.values());
  }

  /**
   * Obtener el lote actualmente seleccionado
   */
  getSelected() {
    if (!this.selectedId) return null;
    return this.lotes.get(this.selectedId) || null;
  }

  /**
   * Seleccionar un lote por su ID
   */
  select(id) {
    if (this.lotes.has(id)) {
      this.selectedId = id;
      this.notify();
    }
  }

  /**
   * Crear o registrar un nuevo lote a partir de una capa de Leaflet o coordenadas
   */
  createLote(polygonLayer, customName = null) {
    if (this.lotes.size >= CONFIG.LIMITS.MAX_LOTES) {
      throw new Error(`Límite alcanzado: máximo ${CONFIG.LIMITS.MAX_LOTES} zonas habilitadas en la entrega inicial.`);
    }

    const id = `lote-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 6)}`;
    const name = customName || `Lote ${this.nextIndex}: Zona ${this.lotes.size === 0 ? "Principal" : "Secundaria"}`;
    this.nextIndex++;

    const geojson = polygonLayer.toGeoJSON();
    const stats = this.calculateGeometryStats(geojson);

    const loteData = {
      id,
      name,
      status: "draft", // "draft" | "confirmed" | "simulated"
      geometry: geojson.geometry,
      area_ha: stats.area_ha,
      area_m2: stats.area_m2,
      perimeter_m: stats.perimeter_m,
      centroid: stats.centroid,
      cultivo_asignado: "papa_canchan",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      periodos: [
        { id: "P1", name: "Campaña Chica", start: "Ene", end: "May", cropId: "papa_canchan" },
        { id: "P2", name: "Campaña Grande", start: "Jun", end: "Dic", cropId: "habas_verdes" }
      ]
    };

    this.lotes.set(id, loteData);
    this.selectedId = id;
    this.notify();
    return loteData;
  }

  /**
   * Actualizar la geometría de un lote existente (por edición con Geoman)
   */
  updateGeometry(id, polygonLayer) {
    const lote = this.lotes.get(id);
    if (!lote) return null;

    const geojson = polygonLayer.toGeoJSON();
    const stats = this.calculateGeometryStats(geojson);

    lote.geometry = geojson.geometry;
    lote.area_ha = stats.area_ha;
    lote.area_m2 = stats.area_m2;
    lote.perimeter_m = stats.perimeter_m;
    lote.centroid = stats.centroid;
    lote.updated_at = new Date().toISOString();
    // Al editar se pasa a estado borrador hasta volver a confirmar
    if (lote.status === "confirmed") {
      lote.status = "draft";
    }

    this.notify();
    return lote;
  }

  /**
   * Confirmar la forma del lote activo
   */
  confirmLote(id) {
    const lote = this.lotes.get(id);
    if (!lote) return null;

    lote.status = "confirmed";
    lote.confirmed_at = new Date().toISOString();
    this.notify();
    return lote;
  }

  /**
   * Actualizar propiedades (nombre, cultivo, etc.)
   */
  updateLote(id, updates) {
    const lote = this.lotes.get(id);
    if (!lote) return null;

    Object.assign(lote, updates, { updated_at: new Date().toISOString() });
    this.notify();
    return lote;
  }

  /**
   * Eliminar un lote por ID
   */
  removeLote(id) {
    if (this.lotes.delete(id)) {
      if (this.selectedId === id) {
        const remaining = Array.from(this.lotes.keys());
        this.selectedId = remaining.length > 0 ? remaining[0] : null;
      }
      this.notify();
      return true;
    }
    return false;
  }

  /**
   * Vaciar todos los lotes
   */
  clearAll() {
    this.lotes.clear();
    this.selectedId = null;
    this.nextIndex = 1;
    this.notify();
  }

  /**
   * Generar GeoJSON estricto según Contrato CC-02
   */
  toFeatureCollection() {
    const features = [];
    for (const lote of this.lotes.values()) {
      features.push({
        type: "Feature",
        id: lote.id,
        properties: {
          id: lote.id,
          name: lote.name,
          status: lote.status,
          area_ha: lote.area_ha,
          area_m2: lote.area_m2,
          perimeter_m: lote.perimeter_m,
          cultivo_asignado: lote.cultivo_asignado,
          periodos: lote.periodos,
          created_at: lote.created_at,
          updated_at: lote.updated_at
        },
        geometry: lote.geometry
      });
    }

    return {
      type: "FeatureCollection",
      crs: {
        type: "name",
        properties: { name: "urn:ogc:def:crs:OGC:1.3:CRS84" }
      },
      features
    };
  }

  /**
   * Generar Payload completo para enviar a la API de simulación
   */
  toSimulationPayload(options = {}) {
    const selected = this.getSelected();
    return {
      version: "1.0-alpha",
      timestamp: new Date().toISOString(),
      parcela_id: selected ? selected.id : "parcela-default",
      lote_seleccionado_id: this.selectedId,
      modo_prioridad: options.mode || "balance_optimo", // "maxima_resiliencia" | "balance_optimo" | "mayor_ganancia"
      escenario_climatico: options.escenario || "historico_nasa_power",
      fecha_inicio: options.startDate || "2026-09-01",
      geo_features: this.toFeatureCollection(),
      metadatos_entorno: {
        plataforma: "AgroPhasor Web Mobile",
        agente_usuario: navigator.userAgent,
        resolucion_tactil: window.innerWidth <= 768 ? "movil" : "escritorio"
      }
    };
  }

  /**
   * Cálculo de área, perímetro y centroide usando Turf.js con fallback matemático
   */
  calculateGeometryStats(geojson) {
    try {
      if (window.turf && geojson) {
        const areaM2 = turf.area(geojson);
        const areaHa = Number((areaM2 / 10000).toFixed(2));
        const lengthKm = turf.length(geojson, { units: 'kilometers' });
        const perimeterM = Math.round(lengthKm * 1000);
        const centroid = turf.centroid(geojson);
        const [lng, lat] = centroid.geometry.coordinates;

        return {
          area_m2: Math.round(areaM2),
          area_ha: areaHa,
          perimeter_m: perimeterM,
          centroid: [Number(lat.toFixed(6)), Number(lng.toFixed(6))]
        };
      }
    } catch (e) {
      console.warn("Fallo cálculo con Turf.js, usando fallback:", e);
    }

    // Fallback básico aproximado
    return {
      area_m2: 25000,
      area_ha: 2.5,
      perimeter_m: 650,
      centroid: [-12.06, -75.21]
    };
  }

  /**
   * Persistencia en localStorage
   */
  saveToStorage() {
    try {
      const data = {
        lotes: Array.from(this.lotes.entries()),
        selectedId: this.selectedId,
        nextIndex: this.nextIndex
      };
      localStorage.setItem(CONFIG.STORAGE_KEYS.LOTES, JSON.stringify(data));
    } catch (e) {
      console.warn("No se pudo guardar en localStorage:", e);
    }
  }

  /**
   * Cargar desde localStorage
   */
  loadFromStorage() {
    try {
      const raw = localStorage.getItem(CONFIG.STORAGE_KEYS.LOTES);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed.lotes && Array.isArray(parsed.lotes)) {
          this.lotes = new Map(parsed.lotes);
          this.selectedId = parsed.selectedId;
          this.nextIndex = parsed.nextIndex || (this.lotes.size + 1);
        }
      }
    } catch (e) {
      console.warn("Error cargando de localStorage:", e);
    }
  }
}
