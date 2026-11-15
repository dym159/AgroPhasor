/**
 * AgroPhasor - Configuración General
 * NASA Space Apps Challenge 2026 - Field Shift
 */

export const CONFIG = {
  // Parcela demo por defecto (Valle del Mantaro, Junín, Perú)
  DEFAULT_LOCATION: {
    name: "Valle del Mantaro - Lote Base",
    department: "Junín",
    country: "Perú",
    latitude: -12.0600,
    longitude: -75.2100,
    elevation_m: 3250,
    zoom: 16
  },

  // Capas de mapas satelitales y vectoriales
  MAP_LAYERS: {
    esriSatellite: {
      name: "Satélite Esri (HD)",
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      attribution: "&copy; Esri &mdash; Fuentes: Esri, Maxar, Earthstar Geographics, y la comunidad GIS",
      maxZoom: 19
    },
    esriLabels: {
      name: "Etiquetas y Caminos",
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      attribution: "&copy; Esri",
      maxZoom: 19
    },
    osm: {
      name: "OpenStreetMap (Mapa de Calles)",
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution: "&copy; Colaboradores de OpenStreetMap",
      maxZoom: 19
    }
  },

  // Configuración de API
  API: {
    BASE_URL: window.location.origin.includes(":8000") 
      ? window.location.origin 
      : "http://localhost:8000",
    SIMULATION_ENDPOINT: "/api/v1/simular",
    PARCELAS_ENDPOINT: "/api/v1/parcelas",
    HEALTH_ENDPOINT: "/api/v1/health",
    TIMEOUT_MS: 15000
  },

  // Almacenamiento local para resiliencia offline
  STORAGE_KEYS: {
    LOTES: "agrophasor_lotes",
    SELECTED_ID: "agrophasor_selected_id",
    PERIODS: "agrophasor_periods",
    ACTIVE_MODE: "agrophasor_active_mode",
    OFFLINE_BACKUP_ENABLED: "agrophasor_offline_backup"
  },

  // Límites según especificación del plan maestro
  LIMITS: {
    MAX_LOTES: 2, // Empezar con 1 y permitir hasta 2 zonas según plan
    MIN_POLYGON_VERTICES: 3
  },

  // Catálogo inicial acordado para la zona andina (Junín / Mantaro)
  CROP_CATALOG: [
    {
      id: "papa_canchan",
      name: "Papa Canchán",
      scientific: "Solanum tuberosum",
      family: "Solanáceas",
      cycle_days: 140,
      biomass_max_t_ha: 14.5,
      harvest_index: 0.68,
      water_need: "Media-Alta",
      icon: "🥔",
      soil_impact: "Extractor de Potasio, cobertura moderada",
      color: "#f59e0b"
    },
    {
      id: "maiz_amilaceo",
      name: "Maíz Blanco Cuzco / Amiláceo",
      scientific: "Zea mays",
      family: "Gramíneas",
      cycle_days: 180,
      biomass_max_t_ha: 18.0,
      harvest_index: 0.45,
      water_need: "Alta",
      icon: "🌽",
      soil_impact: "Gran aporte de rastrojo superficial, demanda Nitrógeno",
      color: "#eab308"
    },
    {
      id: "habas_verdes",
      name: "Habas Verdes / Serranas",
      scientific: "Vicia faba",
      family: "Leguminosas",
      cycle_days: 150,
      biomass_max_t_ha: 9.0,
      harvest_index: 0.52,
      water_need: "Baja-Media",
      icon: "🌱",
      soil_impact: "Fijación biológica de Nitrógeno (+45 kg/ha), recupera suelo",
      color: "#10b981"
    },
    {
      id: "quinua_pasankalla",
      name: "Quinua Pasankalla",
      scientific: "Chenopodium quinoa",
      family: "Amarantáceas",
      cycle_days: 160,
      biomass_max_t_ha: 7.5,
      harvest_index: 0.40,
      water_need: "Baja (Alta resiliencia a heladas)",
      icon: "🌾",
      soil_impact: "Tolerante a salinidad y sequía, bajo consumo hídrico",
      color: "#ec4899"
    },
    {
      id: "avena_forrajera",
      name: "Avena Forrajera / Vicia",
      scientific: "Avena sativa",
      family: "Gramíneas / Cobertura",
      cycle_days: 110,
      biomass_max_t_ha: 12.0,
      harvest_index: 0.80,
      water_need: "Media",
      icon: "🌿",
      soil_impact: "Excelente cobertura contra erosión hídrica en pendiente",
      color: "#06b6d4"
    }
  ]
};
