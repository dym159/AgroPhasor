import { metersPerWorldPixel } from './terrain.js';

/**
 * AgroPhasor - Leaflet and Geoman Map Integration
 * Handles drawing, vertex editing, deletion, satellite layers, and touch controls.
 */

import { CONFIG } from './config.js';

function createImageryTile({ x, y, z }, done) {
  const tile = document.createElement('canvas');
  const size = 256;
  tile.width = size;
  tile.height = size;
  const context = tile.getContext('2d');
  const image = new Image();
  const lowestZoom = Math.max(0, z - 4);
  let sourceZoom = z;

  function requestImage() {
    const scale = 2 ** (z - sourceZoom);
    const column = Math.floor(x / scale);
    const row = Math.floor(y / scale);
    image.onload = () => {
      const width = image.naturalWidth / scale;
      const height = image.naturalHeight / scale;
      context.drawImage(
        image,
        (x - column * scale) * width,
        (y - row * scale) * height,
        width,
        height,
        0,
        0,
        size,
        size
      );
      done(null, tile);
    };
    image.onerror = () => {
      if (sourceZoom === lowestZoom) {
        done(new Error('No image found for this tile.'), tile);
        return;
      }
      sourceZoom -= 1;
      requestImage();
    };
    image.src = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${sourceZoom}/${row}/${column}?blankTile=false`;
  }

  requestImage();
  return tile;
}

export class MapManager {
  constructor(containerId, lotesManager) {
    this.containerId = containerId;
    this.lotesManager = lotesManager;
    this.map = null;
    this.layersByLoteId = new Map(); // loteId -> L.Polygon
    this.baseLayers = {};
    this.overlayLayers = {};
    this.locationLayer = null;
    this.isEditing = false;
    this.activeBaseLayer = "esriSatellite";
  }

  /**
   * Initialize the map and Geoman toolbar
   */
  init() {
    const loc = CONFIG.DEFAULT_LOCATION;

    // Create Leaflet map instance optimized for touch mobile devices
    this.map = L.map(this.containerId, {
      center: [loc.latitude, loc.longitude],
      zoom: loc.zoom,
      maxZoom: 21,
      zoomControl: false, // Reposition zoom control for mobile screens
      tap: true,
      touchZoom: true
    });

    // Place zoom control in a convenient corner
    L.control.zoom({ position: 'topright' }).addTo(this.map);

    // 1. Base layers and NASA GIBS overlays
    const ImageryLayer = L.GridLayer.extend({ createTile: createImageryTile });
    this.baseLayers.esriSatellite = new ImageryLayer({
      attribution: CONFIG.MAP_LAYERS.esriSatellite.attribution,
      maxNativeZoom: CONFIG.MAP_LAYERS.esriSatellite.maxNativeZoom,
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

    this.overlayLayers.nasaHls = L.tileLayer.wms(CONFIG.MAP_LAYERS.nasaHls.url, {
      layers: CONFIG.MAP_LAYERS.nasaHls.layers,
      format: 'image/png',
      transparent: true,
      maxNativeZoom: CONFIG.MAP_LAYERS.nasaHls.maxNativeZoom,
      maxZoom: CONFIG.MAP_LAYERS.nasaHls.maxZoom,
      attribution: CONFIG.MAP_LAYERS.nasaHls.attribution
    });

    // Add satellite imagery and labels by default
    this.baseLayers.esriSatellite.addTo(this.map);
    this.baseLayers.esriLabels.addTo(this.map);

    // Layer switcher for NASA GIBS HLS Sentinel-2 overlay
    L.control.layers(null, { [CONFIG.MAP_LAYERS.nasaHls.name]: this.overlayLayers.nasaHls }, {
      position: 'topright'
    }).addTo(this.map);

    this.locationLayer = L.layerGroup().addTo(this.map);

    // 2. Configure Geoman (Leaflet-Geoman Free)
    this.setupGeoman();

    // 2.1 Configure shield mesh grid overlay
    this.setupMapGrid();

    // 3. Subscribe to lot manager updates
    this.lotesManager.subscribe((lotes, selected) => {
      this.syncMapWithLotes(lotes, selected);
    });

    // 4. If no lots are saved, load the Mantaro Valley demo parcel
    if (this.lotesManager.getAll().length === 0) {
      this.loadDemoParcel();
    }

    return this;
  }

  /**
   * Configure digital terrain grid overlay for the shield effect
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
            // Local relief in top-down view: highlight curvature without shifting georeferencing.
            const neighbors = [sample(x - 64, y), sample(x + 64, y), sample(x, y - 64), sample(x, y + 64)];
            const reference = neighbors.every(v => v !== null) ? neighbors.reduce((a, b) => a + b, 0) / 4 : h;
            return [x, y - 30 * Math.tanh((h - reference) / Math.max(0.2, mpp * 1.5))];
          };
          // Slope shading using normals from the same DEM used by the 3D viewer.
          for (let x = 0; x < size.x; x += 16) for (let y = 0; y < size.y; y += 16) {
            const west = sample(x, y + 8), east = sample(x + 16, y + 8);
            const north = sample(x + 8, y), south = sample(x + 8, y + 16);
            if ([west, east, north, south].some(h => h === null)) continue;
            const gradient = (east - west + south - north) / Math.max(1, 32 * mpp);
            const h = sample(x + 8, y + 8);
            const level = h === null ? 0 : (h - (west + east + north + south) / 4) / Math.max(0.2, mpp * 1.5);
            ctx.globalAlpha = 0.08;
            ctx.fillStyle = terrain.visualColor((left + x + 8) / factor, (top + y + 8) / factor, level, coords.z);
            ctx.fillRect(x, y, 16, 16);
            ctx.globalAlpha = 1;
            ctx.fillStyle = gradient > 0 ? 'rgba(5, 15, 30, 0.04)' : 'rgba(225, 245, 255, 0.03)';
            ctx.fillRect(x, y, 16, 16);
          }
          ctx.strokeStyle = 'rgba(210, 245, 255, 0.28)'; ctx.lineWidth = 0.7;
          ctx.beginPath();
          // Overlap margin so grid curves align seamlessly across tiles.
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
          .then(complete => { if (!complete) ctx.setLineDash([3, 5]); draw(); })
          .catch(() => { ctx.setLineDash([3, 5]); draw(); });
        return tile;
      }
    });
    this.map.createPane('parcelGrid');
    this.map.getPane('parcelGrid').style.zIndex = 350;
    this.map.getPane('parcelGrid').style.pointerEvents = 'none';
    this.gridLayer = new Grid({ pane: 'parcelGrid', tileSize: 256, opacity: 0.45,
      pmIgnore: true, attribution: 'Relief: <a href="https://registry.opendata.aws/terrain-tiles/">Mapzen Terrain Tiles</a>' }).addTo(this.map);
  }

  /**
   * Configure Geoman toolbar with touch-friendly controls
   */
  setupGeoman() {
    if (!this.map.pm) {
      console.error("Leaflet-Geoman is not loaded in the global scope.");
      return;
    }

    // Set UI language to English
    try {
      this.map.pm.setLang('en');
    } catch {
      // Ignore if the language pack is not registered
    }

    // Global Geoman drawing configuration
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
        fillOpacity: 0.12,
        weight: 3
      }
    });

    // Add primary controls required by the master plan:
    // "Use Leaflet-Geoman to draw, edit, and delete contours"
    this.map.pm.addControls({
      position: 'topleft',
      drawPolygon: true,
      drawRectangle: true,
      editMode: true,
      dragMode: true,
      cutPolygon: true, // Allows splitting into 2 zones
      removalMode: true,
      drawMarker: false,
      drawCircleMarker: false,
      drawPolyline: false,
      drawCircle: false,
      drawText: false,
      rotateMode: false
    });

    // Creation events
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

    // Cut events (splitting into 2 zones)
    this.map.on('pm:cut', (e) => {
      console.log("Polygon cut into zones:", e);
      // Update references if a lot is split
    });

    // Deletion event via Geoman
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
   * Bind events to each individual polygon layer
   */
  bindLayerEvents(layer, loteId) {
    layer._agroLoteId = loteId;

    // Select the lot when tapping or clicking the polygon on the map
    layer.on('click', () => {
      this.lotesManager.select(loteId);
    });

    // When editing vertices or dragging
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
   * Synchronize the map when lots change in LotesManager
   */
  syncMapWithLotes(lotes, selected) {
    const existingIds = new Set(this.layersByLoteId.keys());
    const currentIds = new Set(lotes.map(l => l.id));

    // Remove map layers that no longer exist in the manager
    for (const [id, layer] of this.layersByLoteId.entries()) {
      if (!currentIds.has(id)) {
        this.map.removeLayer(layer);
        this.layersByLoteId.delete(id);
      }
    }

    // Create or update existing layers
    lotes.forEach(lote => {
      let layer = this.layersByLoteId.get(lote.id);
      if (!layer) {
        // Rebuild layer from its GeoJSON (e.g., after reloading from localStorage)
        const geojsonFeature = {
          type: "Feature",
          geometry: lote.geometry
        };

        const tempGeoJsonGroup = L.geoJSON(geojsonFeature, {
          style: () => this.getPolygonStyle(lote, selected && selected.id === lote.id)
        });

        // Extract the first polygon layer
        tempGeoJsonGroup.eachLayer(l => {
          layer = l;
        });

        if (layer) {
          layer.addTo(this.map);
          this.layersByLoteId.set(lote.id, layer);
          this.bindLayerEvents(layer, lote.id);
        }
      }

      // Update visual style according to selection and confirmation state
      if (layer) {
        const isSelected = selected && selected.id === lote.id;
        layer.setStyle(this.getPolygonStyle(lote, isSelected));
      }
    });
  }

  showParcelTemperatures(cells) {
    this.parcelTemperatures?.remove();
    this.parcelTemperatures = null;
    if (!cells.length) return;
    this.parcelTemperatures = L.geoJSON(cells.map(cell => ({
      type: 'Feature',
      geometry: cell.geometry,
      properties: cell
    })), {
      pmIgnore: true,
      style: ({ properties: { mean_canopy_temp: mean } }) => ({
        pmIgnore: true,
        color: '#f8fafc',
        weight: 1,
        fillColor: `hsl(${Math.max(0, Math.min(220, 220 - mean * 7))}, 85%, 50%)`,
        fillOpacity: 0.45
      }),
      onEachFeature: ({ properties: cell }, layer) => {
        layer.bindTooltip(
          `Cell ${cell.cell_id} · ${cell.latitude.toFixed(5)}°, ${cell.longitude.toFixed(5)}°<br>`
          + `Mean canopy ${cell.mean_canopy_temp} °C · min ${cell.min_canopy_temp} °C · max ${cell.max_canopy_temp} °C<br>`
          + `SRTM ${cell.altitude_m.toFixed(0)} m · slope ${cell.slope_deg.toFixed(1)}°`
        );
      }
    }).addTo(this.map);
  }

  /**
   * Visual style by state and selection with "Protective Shield" aesthetics
   */
  getPolygonStyle(lote, isSelected) {
    const isConfirmed = lote.status === "confirmed";

    if (isSelected) {
      return {
        className: 'agro-shield-polygon',
        color: isConfirmed ? '#10b981' : '#38bdf8',
        fillColor: isConfirmed ? '#10b981' : '#0284c7',
        fillOpacity: 0.12,
        weight: 3.5,
        dashArray: isConfirmed ? null : '6, 6'
      };
    }

    return {
      className: isConfirmed ? 'agro-shield-confirmed' : '',
      color: isConfirmed ? '#059669' : '#94a3b8',
      fillColor: isConfirmed ? '#10b981' : '#64748b',
      fillOpacity: 0.08,
      weight: 2,
      dashArray: isConfirmed ? null : '4, 4'
    };
  }

  /**
   * Update lot layer style
   */
  updateLayerStyles(loteId, isSelected) {
    const layer = this.layersByLoteId.get(loteId);
    const lote = this.lotesManager.lotes.get(loteId);
    if (layer && lote) {
      layer.setStyle(this.getPolygonStyle(lote, isSelected));
    }
  }

  /**
   * Center map on the selected lot
   */
  zoomToLote(loteId) {
    const layer = this.layersByLoteId.get(loteId);
    if (layer && layer.getBounds) {
      this.map.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 18 });
    }
  }

  /**
   * Switch between satellite imagery and vector street map
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
   * Center map on a place returned by search
   */
  centerOnPlace(lat, lon, zoom = 15) {
    this.map.setView([lat, lon], zoom);
  }

  /**
   * User geolocation ("My Location") with permission handling
   */
  locateUser(onSuccess, onError) {
    if (!window.isSecureContext || !navigator.geolocation) {
      if (onError) {
        onError(new Error("Location access requires a supported browser and secure context. You can pan the map manually."));
      }
      return;
    }

    const locationErrors = {
      1: "Location permission is blocked. Allow it in this site's settings.",
      2: "The device could not determine your location. Check location services and try again.",
      3: "Location lookup timed out. Check for any pending permission prompt and try again."
    };

    let waiting = true;
    const finish = () => {
      waiting = false;
      window.clearTimeout(timeout);
    };
    const handleError = ({ code }) => {
      if (!waiting) return;
      finish();
      const message = locationErrors[code] || "Could not determine your location.";
      console.warn("Geolocation denied or unavailable, keeping demo parcel:", message);
      if (onError) onError(new Error(`${message} You can pan the map manually.`));
    };

    // Browser timeout may exclude permission prompt wait time.
    const timeout = window.setTimeout(() => handleError({ code: 3 }), 25000);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        if (!waiting) return;
        finish();
        const { latitude, longitude, accuracy } = coords;
        const position = [latitude, longitude];
        this.locationLayer.clearLayers();
        if (Number.isFinite(accuracy) && accuracy > 0) {
          L.circle(position, { radius: accuracy, weight: 1, color: '#38bdf8' }).addTo(this.locationLayer);
        }
        const userMarker = L.circleMarker(position, {
          radius: 7,
          color: '#ffffff',
          fillColor: '#10b981',
          fillOpacity: 1,
          weight: 2.5
        }).addTo(this.locationLayer);

        userMarker.bindPopup("📍 You are here").openPopup();
        this.map.setView(position, 15);
        if (onSuccess) onSuccess(coords);
      },
      handleError,
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 60000 }
    );
  }

  /**
   * Load the Mantaro Valley demo parcel (-12.06, -75.21)
   */
  loadDemoParcel() {
    // ~2.4 ha polygon on agricultural terraces in Junin
    const demoCoords = [
      [-12.0592, -75.2115],
      [-12.0588, -75.2095],
      [-12.0610, -75.2090],
      [-12.0615, -75.2110]
    ];

    const demoPolygon = L.polygon(demoCoords);
    demoPolygon.addTo(this.map);

    const lote = this.lotesManager.createLote(demoPolygon, "Lot 1: Mantaro Parcel");
    demoPolygon._agroLoteId = lote.id;
    this.layersByLoteId.set(lote.id, demoPolygon);
    this.bindLayerEvents(demoPolygon, lote.id);

    // Confirm initially so the user can simulate right away
    this.lotesManager.confirmLote(lote.id);
    this.map.fitBounds(demoPolygon.getBounds(), { padding: [60, 60] });
  }

  /**
   * Manually activate the Geoman polygon drawing tool
   */
  startDrawPolygon() {
    if (this.map.pm) {
      this.map.pm.enableDraw('Polygon');
    }
  }

  /**
   * Activate polygon vertex editing mode
   */
  startEditMode() {
    if (this.map.pm) {
      this.map.pm.toggleGlobalEditMode();
    }
  }
}
