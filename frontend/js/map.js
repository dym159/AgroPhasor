import { metersPerWorldPixel } from './terrain.js';

/**
 * AgroPhasor - Integración de Mapa Leaflet y Geoman
 * Manejo de dibujo, edición de vértices, eliminación, capas satelitales y controles táctiles.
 */

import { CONFIG } from './config.js';

export class MapManager {
  constructor(containerId, lotesManager) {
    this.containerId = containerId;
    this.lotesManager = lotesManager;
    this.map = null;
    this.layersByLoteId = new Map(); // loteId -> L.Polygon
    this.baseLayers = {};
    this.isEditing = false;
    this.activeBaseLayer = "esriSatellite";
  }

  /**
   * Inicializar el mapa y la barra de Geoman
   */
  init() {
    const loc = CONFIG.DEFAULT_LOCATION;

    // Crear instancia de mapa Leaflet optimizada para dispositivos móviles táctiles
    this.map = L.map(this.containerId, {
      center: [loc.latitude, loc.longitude],
      zoom: loc.zoom,
      zoomControl: false, // Reubicaremos el control de zoom para pantallas móviles
      tap: true,
      touchZoom: true
    });

    // Control de zoom en posición cómoda
    L.control.zoom({ position: 'topright' }).addTo(this.map);

    // 1. Capas base
    this.baseLayers.esriSatellite = L.tileLayer(CONFIG.MAP_LAYERS.esriSatellite.url, {
      attribution: CONFIG.MAP_LAYERS.esriSatellite.attribution,
      maxZoom: CONFIG.MAP_LAYERS.esriSatellite.maxZoom
    });

    this.baseLayers.esriLabels = L.tileLayer(CONFIG.MAP_LAYERS.esriLabels.url, {
      attribution: CONFIG.MAP_LAYERS.esriLabels.attribution,
      maxZoom: CONFIG.MAP_LAYERS.esriLabels.maxZoom
    });

    this.baseLayers.osm = L.tileLayer(CONFIG.MAP_LAYERS.osm.url, {
      attribution: CONFIG.MAP_LAYERS.osm.attribution,
      maxZoom: CONFIG.MAP_LAYERS.osm.maxZoom
    });

    // Añadir satélite y etiquetas por defecto
    this.baseLayers.esriSatellite.addTo(this.map);
    this.baseLayers.esriLabels.addTo(this.map);

    // 2. Configurar Geoman (Leaflet-Geoman Free)
    this.setupGeoman();

    // 2.1 Configurar patrón de malla de escudo
    this.setupMapGrid();

    // 3. Suscribirse a cambios del gestor de lotes
    this.lotesManager.subscribe((lotes, selected) => {
      this.syncMapWithLotes(lotes, selected);
    });

    // 4. Si no hay lotes guardados, cargar parcela demo del Valle del Mantaro
    if (this.lotesManager.getAll().length === 0) {
      this.loadDemoParcel();
    }

    return this;
  }

  /**
   * Configurar patrón SVG de malla digital para el efecto de escudo
   */
  setupMapGrid() {
    const terrain = this.terrain;
    const Grid = L.GridLayer.extend({
      createTile(coords, done) {
        const tile = document.createElement('canvas');
        const size = this.getTileSize();
        const dpr = window.devicePixelRatio || 1;
        tile.width = size.x * dpr; tile.height = size.y * dpr;
        tile.style.width = size.x + 'px'; tile.style.height = size.y + 'px';
        const ctx = tile.getContext('2d');
        ctx.scale(dpr, dpr);
        const factor = 2 ** coords.z;
        const left = coords.x * size.x, top = coords.y * size.y;
        const draw = () => {
          const sample = (x, y) => terrain.height((left + x) / factor, (top + y) / factor, coords.z);
          const mpp = metersPerWorldPixel((top + 128) / factor) / factor;
          const vertex = (x, y) => {
            const h = sample(x, y);
            if (h === null) return [x, y];
            // Relieve local en vista cenital: resaltar curvatura sin desplazar la georreferencia.
            const neighbors = [sample(x - 64, y), sample(x + 64, y), sample(x, y - 64), sample(x, y + 64)];
            const reference = neighbors.every(v => v !== null) ? neighbors.reduce((a, b) => a + b, 0) / 4 : h;
            return [x, y - 18 * Math.tanh((h - reference) / Math.max(1, mpp * 12))];
          };
          // Sombreado por normales del mismo DEM que utiliza el visor 3D.
          for (let x = 0; x < size.x; x += 16) for (let y = 0; y < size.y; y += 16) {
            const west = sample(x, y + 8), east = sample(x + 16, y + 8);
            const north = sample(x + 8, y), south = sample(x + 8, y + 16);
            if ([west, east, north, south].some(h => h === null)) continue;
            const gradient = (east - west + south - north) / Math.max(1, 32 * mpp);
            ctx.fillStyle = gradient > 0 ? 'rgba(5, 15, 30, 0.18)' : 'rgba(186, 230, 253, 0.10)';
            ctx.fillRect(x, y, 16, 16);
          }
          ctx.strokeStyle = 'rgba(125, 211, 252, 0.65)'; ctx.lineWidth = 1;
          ctx.beginPath();
          // Margen para que las curvas coincidan sin costuras entre teselas.
          for (let x = -32; x <= size.x + 32; x += 32) {
            for (let y = -32; y <= size.y + 32; y += 4) {
              const p = vertex(x, y); if (y === -32) ctx.moveTo(...p); else ctx.lineTo(...p);
            }
          }
          for (let y = -32; y <= size.y + 32; y += 32) {
            for (let x = -32; x <= size.x + 32; x += 4) {
              const p = vertex(x, y); if (x === -32) ctx.moveTo(...p); else ctx.lineTo(...p);
            }
          }
          ctx.stroke();
          done(null, tile);
        };
        terrain.loadBounds((left - 100) / factor, (top - 100) / factor,
          (left + size.x + 100) / factor, (top + size.y + 100) / factor, coords.z)
          .then(draw).catch(() => { ctx.setLineDash([3, 5]); draw(); });
        return tile;
      }
    });
    this.map.createPane('parcelGrid');
    this.map.getPane('parcelGrid').style.zIndex = 350;
    this.map.getPane('parcelGrid').style.pointerEvents = 'none';
    this.gridLayer = new Grid({ pane: 'parcelGrid', tileSize: 256, opacity: 0.8,
      pmIgnore: true, attribution: 'Relieve: <a href="https://registry.opendata.aws/terrain-tiles/">Mapzen Terrain Tiles</a>' }).addTo(this.map);
  }

  /**
   * Configurar barra de herramientas Geoman con controles táctiles amigables
   */
  setupGeoman() {
    if (!this.map.pm) {
      console.error("Leaflet-Geoman no está cargado en el entorno global.");
      return;
    }

    // Idioma español
    try {
      this.map.pm.setLang('es');
    } catch {
      // Ignorar si no está registrado el paquete de idioma
    }

    // Configuración global de dibujo de Geoman
    this.map.pm.setGlobalOptions({
      snappable: true,
      snapDistance: 25,
      allowSelfIntersection: false,
      templineStyle: {
        color: '#10b981',
        weight: 3
      },
      hintlineStyle: {
        color: '#34d399',
        dashArray: [6, 6]
      },
      pathOptions: {
        color: '#10b981',
        fillColor: '#10b981',
        fillOpacity: 0.35,
        weight: 3
      }
    });

    // Añadir controles principales requeridos por el plan maestro:
    // "Usar Leaflet-Geoman para dibujar, editar y eliminar contornos"
    this.map.pm.addControls({
      position: 'topleft',
      drawPolygon: true,
      drawRectangle: true,
      editMode: true,
      dragMode: true,
      cutPolygon: true, // Permite partir en 2 zonas
      removalMode: true,
      drawMarker: false,
      drawCircleMarker: false,
      drawPolyline: false,
      drawCircle: false,
      drawText: false,
      rotateMode: false
    });

    // Eventos de creación
    this.map.on('pm:create', (e) => {
      if (e.shape === 'Polygon' || e.shape === 'Rectangle') {
        const layer = e.layer;
        try {
          const lote = this.lotesManager.createLote(layer);
          layer._agroLoteId = lote.id;
          this.layersByLoteId.set(lote.id, layer);
          this.bindLayerEvents(layer, lote.id);
          this.updateLayerStyles(lote.id, true);
        } catch (err) {
          alert(err.message);
          this.map.removeLayer(layer);
        }
      }
    });

    // Eventos de corte (división en 2 zonas)
    this.map.on('pm:cut', (e) => {
      console.log("Polígono cortado en zonas:", e);
      // Actualizar referencias si se divide un lote
    });

    // Evento de eliminación por Geoman
    this.map.on('pm:remove', (e) => {
      const layer = e.layer;
      const loteId = layer._agroLoteId;
      if (loteId) {
        this.layersByLoteId.delete(loteId);
        this.lotesManager.removeLote(loteId);
      }
    });
  }

  /**
   * Conectar eventos a cada capa de polígono individual
   */
  bindLayerEvents(layer, loteId) {
    layer._agroLoteId = loteId;

    // Al tocar o hacer clic sobre el polígono en el mapa, seleccionarlo
    layer.on('click', () => {
      this.lotesManager.select(loteId);
    });

    // Al editar vértices o mover
    layer.on('pm:edit', () => {
      this.lotesManager.updateGeometry(loteId, layer);
    });

    layer.on('pm:dragend', () => {
      this.lotesManager.updateGeometry(loteId, layer);
    });

    layer.on('pm:vertexchange', () => {
      this.lotesManager.updateGeometry(loteId, layer);
    });
  }

  /**
   * Sincronizar el mapa cuando cambian los lotes en el LotesManager
   */
  syncMapWithLotes(lotes, selected) {
    const existingIds = new Set(this.layersByLoteId.keys());
    const currentIds = new Set(lotes.map(l => l.id));

    // Eliminar capas en mapa que ya no existan en el gestor
    for (const [id, layer] of this.layersByLoteId.entries()) {
      if (!currentIds.has(id)) {
        this.map.removeLayer(layer);
        this.layersByLoteId.delete(id);
      }
    }

    // Crear o actualizar capas existentes
    lotes.forEach(lote => {
      let layer = this.layersByLoteId.get(lote.id);
      if (!layer) {
        // Reconstruir la capa desde su GeoJSON (por ejemplo tras recargar de localStorage)
        const geojsonFeature = {
          type: "Feature",
          geometry: lote.geometry
        };

        const tempGeoJsonGroup = L.geoJSON(geojsonFeature, {
          style: () => this.getPolygonStyle(lote, selected && selected.id === lote.id)
        });

        // Extraer la primera capa polígono
        tempGeoJsonGroup.eachLayer(l => {
          layer = l;
        });

        if (layer) {
          layer.addTo(this.map);
          this.layersByLoteId.set(lote.id, layer);
          this.bindLayerEvents(layer, lote.id);
        }
      }

      // Actualizar estilo visual según si está seleccionado o confirmado
      if (layer) {
        const isSelected = selected && selected.id === lote.id;
        layer.setStyle(this.getPolygonStyle(lote, isSelected));
      }
    });
  }

  /**
   * Estilo visual según estado y selección con estética de "Escudo Protector"
   */
  getPolygonStyle(lote, isSelected) {
    const isConfirmed = lote.status === "confirmed";

    if (isSelected) {
      return {
        className: 'agro-shield-polygon',
        color: isConfirmed ? '#10b981' : '#38bdf8',
        fillColor: isConfirmed ? '#10b981' : '#0284c7',
        fillOpacity: 0.40,
        weight: 3.5,
        dashArray: isConfirmed ? null : '6, 6'
      };
    }

    return {
      className: isConfirmed ? 'agro-shield-confirmed' : '',
      color: isConfirmed ? '#059669' : '#94a3b8',
      fillColor: isConfirmed ? '#10b981' : '#64748b',
      fillOpacity: 0.22,
      weight: 2,
      dashArray: isConfirmed ? null : '4, 4'
    };
  }

  /**
   * Actualizar estilo del lote
   */
  updateLayerStyles(loteId, isSelected) {
    const layer = this.layersByLoteId.get(loteId);
    const lote = this.lotesManager.lotes.get(loteId);
    if (layer && lote) {
      layer.setStyle(this.getPolygonStyle(lote, isSelected));
    }
  }

  /**
   * Centrar el mapa sobre el lote seleccionado
   */
  zoomToLote(loteId) {
    const layer = this.layersByLoteId.get(loteId);
    if (layer && layer.getBounds) {
      this.map.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 18 });
    }
  }

  /**
   * Alternar entre mapa satelital y mapa vectorial
   */
  toggleBaseLayer(layerKey) {
    if (this.baseLayers[layerKey]) {
      this.map.removeLayer(this.baseLayers.esriSatellite);
      this.map.removeLayer(this.baseLayers.osm);

      if (layerKey === "esriSatellite") {
        this.baseLayers.esriSatellite.addTo(this.map);
        this.baseLayers.esriLabels.addTo(this.map);
      } else {
        this.map.removeLayer(this.baseLayers.esriLabels);
        this.baseLayers.osm.addTo(this.map);
      }
      this.activeBaseLayer = layerKey;
    }
  }

  /**
   * Geolocalización del usuario ("Mi Ubicación") con manejo de permisos
   */
  locateUser(onSuccess, onError) {
    if (!navigator.geolocation) {
      if (onError) onError(new Error("Tu navegador no soporta geolocalización."));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        this.map.setView([latitude, longitude], 17);

        // Marcador discreto de posición del agricultor
        const userMarker = L.circleMarker([latitude, longitude], {
          radius: 8,
          color: '#ffffff',
          fillColor: '#3b82f6',
          fillOpacity: 0.9,
          weight: 3
        }).addTo(this.map);

        userMarker.bindPopup("📍 Estás aquí").openPopup();
        if (onSuccess) onSuccess(pos.coords);
      },
      (err) => {
        console.warn("Geolocalización rechazada o inaccesible, manteniendo parcela demo:", err);
        if (onError) onError(err);
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }

  /**
   * Cargar la parcela de demostración del Valle del Mantaro (-12.06, -75.21)
   */
  loadDemoParcel() {
    // Polígono de ~2.4 ha en terrazas agrícolas de Junín
    const demoCoords = [
      [-12.0592, -75.2115],
      [-12.0588, -75.2095],
      [-12.0610, -75.2090],
      [-12.0615, -75.2110]
    ];

    const demoPolygon = L.polygon(demoCoords);
    demoPolygon.addTo(this.map);

    const lote = this.lotesManager.createLote(demoPolygon, "Lote 1: Parcela El Mantaro");
    demoPolygon._agroLoteId = lote.id;
    this.layersByLoteId.set(lote.id, demoPolygon);
    this.bindLayerEvents(demoPolygon, lote.id);

    // Confirmarla inicialmente para que el usuario pueda simular de inmediato
    this.lotesManager.confirmLote(lote.id);
    this.map.fitBounds(demoPolygon.getBounds(), { padding: [60, 60] });
  }

  /**
   * Activar manualmente la herramienta de dibujo de polígono con Geoman
   */
  startDrawPolygon() {
    if (this.map.pm) {
      this.map.pm.enableDraw('Polygon');
    }
  }

  /**
   * Activar modo de edición de vértices del polígono
   */
  startEditMode() {
    if (this.map.pm) {
      this.map.pm.toggleGlobalEditMode();
    }
  }
}
