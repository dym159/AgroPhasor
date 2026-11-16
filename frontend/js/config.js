/**
 * AgroPhasor - General Configuration
 * NASA Space Apps Challenge 2026 - Field Shift
 */

export const CONFIG = {
  // Default demo parcel (Mantaro Valley, Junin, Peru)
  DEFAULT_LOCATION: {
    name: "Mantaro Valley - Base Lot",
    department: "Junin",
    country: "Peru",
    latitude: -12.0600,
    longitude: -75.2100,
    elevation_m: 3250,
    zoom: 16
  },

  // Satellite and vector map layers
  MAP_LAYERS: {
    esriSatellite: {
      name: "Esri Satellite (HD)",
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      attribution: '<a href="https://goto.arcgisonline.com/maps/World_Imagery">Esri World Imagery</a> · Esri, Vantor, Earthstar Geographics and the GIS community',
      maxNativeZoom: 19,
      maxZoom: 21
    },
    esriLabels: {
      name: "Labels and Roads",
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      attribution: "&copy; Esri",
      maxZoom: 19
    },
    osm: {
      name: "OpenStreetMap (Street Map)",
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19
    },
    nasaHls: {
      name: "NASA HLS · Sentinel-2",
      url: "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
      layers: "HLS_S30_Nadir_BRDF_Adjusted_Reflectance",
      attribution: '<a href="https://www.earthdata.nasa.gov/data/tools/gibs">NASA GIBS</a> · HLS Sentinel-2',
      maxNativeZoom: 13,
      maxZoom: 21
    }
  },

  // API configuration
  API: {
    BASE_URL: "",
    SIMULATION_ENDPOINT: "/api/v1/simular",
    PARCELAS_ENDPOINT: "/api/v1/parcelas",
    HEALTH_ENDPOINT: "/api/v1/health",
    PLACES_ENDPOINT: "/api/places",
    TIMEOUT_MS: 15000
  },

  // Local storage for offline resilience
  STORAGE_KEYS: {
    LOTES: "agrophasor_lotes",
    SELECTED_ID: "agrophasor_selected_id",
    PERIODS: "agrophasor_periods",
    ACTIVE_MODE: "agrophasor_active_mode",
    OFFLINE_BACKUP_ENABLED: "agrophasor_offline_backup"
  },

  // Limits per master plan specification
  LIMITS: {
    MAX_LOTES: 2, // Start with 1 and allow up to 2 zones per plan
    MIN_POLYGON_VERTICES: 3
  },

  // Initial crop catalog calibrated for the Andean region (Junin / Mantaro)
  CROP_CATALOG: [
    {
      id: "papa_canchan",
      name: "Canchan Potato",
      scientific: "Solanum tuberosum",
      family: "Solanaceae",
      cycle_days: 140,
      biomass_max_t_ha: 14.5,
      harvest_index: 0.68,
      water_need: "Medium-High",
      icon: "🥔",
      soil_impact: "Potassium extractor, moderate canopy cover",
      color: "#f59e0b"
    },
    {
      id: "maiz_amilaceo",
      name: "Cusco White / Amylaceous Maize",
      scientific: "Zea mays",
      family: "Poaceae",
      cycle_days: 180,
      biomass_max_t_ha: 18.0,
      harvest_index: 0.45,
      water_need: "High",
      icon: "🌽",
      soil_impact: "Large surface stover input, demands Nitrogen",
      color: "#eab308"
    },
    {
      id: "habas_verdes",
      name: "Green Fava Beans",
      scientific: "Vicia faba",
      family: "Fabaceae",
      cycle_days: 150,
      biomass_max_t_ha: 9.0,
      harvest_index: 0.52,
      water_need: "Low-Medium",
      icon: "🌱",
      soil_impact: "Biological Nitrogen fixation (+45 kg/ha), restores soil",
      color: "#10b981"
    },
    {
      id: "quinua_pasankalla",
      name: "Pasankalla Quinoa",
      scientific: "Chenopodium quinoa",
      family: "Amaranthaceae",
      cycle_days: 160,
      biomass_max_t_ha: 7.5,
      harvest_index: 0.40,
      water_need: "Low (High frost resilience)",
      icon: "🌾",
      soil_impact: "Salinity- and drought-tolerant, low water consumption",
      color: "#ec4899"
    },
    {
      id: "avena_forrajera",
      name: "Forage Oat / Vetch",
      scientific: "Avena sativa",
      family: "Poaceae / Cover",
      cycle_days: 110,
      biomass_max_t_ha: 12.0,
      harvest_index: 0.80,
      water_need: "Medium",
      icon: "🌿",
      soil_impact: "Excellent cover against water erosion on slopes",
      color: "#06b6d4"
    }
  ]
};
