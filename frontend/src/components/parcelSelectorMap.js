import { searchPlaces } from '../services/agroApi.js';
import { clearChildren, createElement } from '../utils/dom.js';

const ESRI_ATTRIBUTION =
  '<a href="https://goto.arcgisonline.com/maps/World_Imagery">Esri World Imagery</a> · Esri, Maxar, Earthstar Geographics';
const NASA_HLS_WMS_URL = 'https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi';

function createOverzoomImageryTile({ x, y, z }, done) {
  const tile = document.createElement('canvas');
  const size = 256;
  tile.width = size;
  tile.height = size;
  const context = tile.getContext('2d');
  const image = new Image();
  const lowestZoom = Math.max(0, z - 4);
  let sourceZoom = Math.min(z, 18);

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
      if (sourceZoom <= lowestZoom) {
        done(new Error('Sin imagen satelital para esta tesela.'), tile);
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

export function mountParcelSelectorMap(container, state, callbacks) {
  if (!container) return { update: () => {}, destroy: () => {} };

  clearChildren(container);

  let activeLeafletMap = null;
  let activePolygonLayer = null;
  let activeThermalLayer = null;
  let lastCells;

  const searchForm = createPlaceSearchControl((place) => {
    if (activeLeafletMap) {
      activeLeafletMap.setView([place.lat, place.lon], 16);
    }
  });

  const locateBtn = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Mi ubicación',
    onClick: handleGeolocation,
  });

  const deleteBtn = createElement('button', {
    type: 'button',
    className: 'btn btn-danger',
    text: 'Eliminar terreno',
    attrs: state.hasActiveTerrain ? {} : { disabled: 'true' },
    onClick: () => {
      if (activePolygonLayer) {
        activePolygonLayer.remove();
        activePolygonLayer = null;
      }
      if (activeThermalLayer) {
        activeThermalLayer.remove();
        activeThermalLayer = null;
      }
      callbacks.onDeleteTerrain();
    },
  });

  const confirmBtn = createElement('button', {
    type: 'button',
    className: 'btn btn-accent',
    text: 'Confirmar terreno',
    attrs: state.hasActiveTerrain ? {} : { disabled: 'true' },
    onClick: () => {
      if (!state.hasActiveTerrain) return;
      callbacks.onConfirmTerrain();
    },
  });

  const rightControls = createElement('div', { className: 'stage-presets' }, [
    searchForm,
    locateBtn,
    deleteBtn,
    confirmBtn,
  ]);

  const toolbar = createElement('div', { className: 'stage-toolbar' }, [
    rightControls,
  ]);

  const statusText = createElement('span', { attrs: { role: 'status' } });
  const retryButton = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Reintentar',
    onClick: callbacks.onRetrySimulation,
  });
  const statusBar = createElement('div', {
    className: 'edo1-status-bar',
  }, [statusText, retryButton]);
  function updateStatus(nextState) {
    statusText.textContent = nextState.parcelSimulationStatusText;
    retryButton.hidden = !nextState.parcelSimulationFailed;
  }
  updateStatus(state);

  const body = createElement('div', { className: 'stage-body' }, [statusBar]);
  container.append(toolbar, body);

  if (typeof window.L === 'undefined') {
    renderFallbackSelector(body);
    return { update: updateStatus, destroy: () => {} };
  }

  const mapHost = createElement('div', { className: 'leaflet-map-host' });
  body.append(mapHost);

  const mapSetup = initializeLeafletMap(
    mapHost,
    state.selectedParcel,
    state.hasActiveTerrain,
    (layer, polygonCoords) => {
      if (activePolygonLayer) {
        activePolygonLayer.remove();
      }
      activePolygonLayer = layer;
      callbacks.onCustomPolygonDrawn(polygonCoords);
    }
  );

  activeLeafletMap = mapSetup.map;
  activePolygonLayer = mapSetup.polygonLayer;

  renderThermalCells(state.parcelSimulationResult?.cells);

  requestAnimationFrame(() => {
    if (activeLeafletMap) activeLeafletMap.invalidateSize();
  });

  function renderThermalCells(cells) {
    if (cells === lastCells) return;
    lastCells = cells;
    if (activeThermalLayer) {
      activeThermalLayer.remove();
      activeThermalLayer = null;
    }
    if (!activeLeafletMap || !Array.isArray(cells) || !cells.length) return;

    const L = window.L;
    activeThermalLayer = L.geoJSON(
      cells.map((cell) => ({
        type: 'Feature',
        geometry: cell.geometry,
        properties: cell,
      })),
      {
        pmIgnore: true,
        style: ({ properties: cell }) => ({
          pmIgnore: true,
          color: '#f8fafc',
          weight: 1,
          fillColor: cell.shield_enabled
            ? `hsl(${Math.max(0, Math.min(220, 220 - cell.mean_canopy_temp * 7))}, 85%, 50%)`
            : `rgb(${cell.soil_color_rgb.join(',')})`,
          fillOpacity: 0.42,
        }),
        onEachFeature: ({ properties: cell }, layer) => {
          layer.bindTooltip(
            `Celda ${cell.cell_id} · ${cell.latitude.toFixed(5)}°, ${cell.longitude.toFixed(5)}°<br>` +
              (cell.shield_enabled
                ? `Dosel medio ${cell.mean_canopy_temp} °C (mín ${cell.min_canopy_temp} °C / máx ${cell.max_canopy_temp} °C)<br>`
                : 'Suelo desnudo · Exposición a la lluvia<br>') +
              `SRTM ${cell.altitude_m.toFixed(1)} m · pendiente ${cell.slope_deg.toFixed(1)}°<br>` +
              `Fertilidad ${Math.round(cell.eta_nutrientes * 100)} % · limitante ${cell.limiting_nutrient}`
          );
        },
      }
    ).addTo(activeLeafletMap);
  }

  function handleGeolocation() {
    if (!navigator.geolocation || !activeLeafletMap) return;

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        if (activeLeafletMap) {
          activeLeafletMap.setView([latitude, longitude], 16);
        }
      },
      () => {},
      { timeout: 8000 }
    );
  }

  function update(nextState) {
    updateStatus(nextState);
    renderThermalCells(nextState.parcelSimulationResult?.cells);
  }

  return {
    update,
    destroy: () => {
      if (activeLeafletMap) {
        activeLeafletMap.stop();
        activeLeafletMap.remove();
        activeLeafletMap = null;
      }
    },
  };
}

function createPlaceSearchControl(onSelectPlace) {
  const input = createElement('input', {
    type: 'search',
    className: 'stage-search-input',
    attrs: {
      placeholder: 'Buscar localidad...',
      'aria-label': 'Buscar distrito, ciudad o valle',
    },
  });

  const resultsList = createElement('ul', {
    className: 'stage-search-results',
    attrs: { hidden: 'true' },
  });

  const form = createElement('form', { className: 'stage-search-form' }, [
    input,
    resultsList,
  ]);

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = input.value.trim();
    if (query.length < 2) return;

    clearChildren(resultsList);
    resultsList.hidden = true;

    try {
      const places = await searchPlaces(query);
      if (!places.length) return;

      for (const place of places) {
        const btn = createElement('button', {
          type: 'button',
          className: 'stage-search-item',
          text: place.name,
          onClick: () => {
            resultsList.hidden = true;
            onSelectPlace(place);
          },
        });
        resultsList.append(createElement('li', {}, [btn]));
      }
      resultsList.hidden = false;
    } catch {
      resultsList.hidden = true;
    }
  });

  return form;
}

function initializeLeafletMap(mapHost, parcel, hasActiveTerrain, onPolygonCreated) {
  const L = window.L;
  const map = L.map(mapHost, {
    zoomControl: true,
    maxZoom: 21,
    zoomAnimation: false,
    fadeAnimation: false,
  }).setView(parcel?.center ?? [-9.19, -75.02], parcel ? 16 : 5);

  const OverzoomImagery = L.GridLayer.extend({
    createTile: createOverzoomImageryTile,
  });
  new OverzoomImagery({
    attribution: ESRI_ATTRIBUTION,
    maxNativeZoom: 18,
    maxZoom: 21,
  }).addTo(map);

  const nasaHlsLayer = L.tileLayer.wms(NASA_HLS_WMS_URL, {
    layers: 'HLS_S30_Nadir_BRDF_Adjusted_Reflectance',
    format: 'image/png',
    transparent: true,
    maxNativeZoom: 13,
    maxZoom: 21,
    attribution: 'NASA GIBS · HLS Sentinel-2',
  });

  L.control
    .layers(null, { 'NASA HLS · Sentinel-2': nasaHlsLayer }, { position: 'topright' })
    .addTo(map);

  let polygonLayer = null;
  if (hasActiveTerrain && parcel.polygon?.length) {
    polygonLayer = L.polygon(parcel.polygon, {
      color: '#38bdf8',
      fillColor: '#22c55e',
      fillOpacity: 0.22,
      weight: 2,
    }).addTo(map);
    map.fitBounds(polygonLayer.getBounds(), {
      padding: [45, 45],
      maxZoom: 17,
      animate: false,
    });
  }

  if (map.pm) {
    map.pm.addControls({
      position: 'topleft',
      drawCircle: false,
      drawCircleMarker: false,
      drawMarker: false,
      drawPolyline: false,
      drawText: false,
      cutPolygon: false,
      rotateMode: false,
      drawPolygon: true,
      drawRectangle: true,
      editMode: true,
      removalMode: true,
    });

    map.on('pm:create', (event) => {
      if (polygonLayer) {
        polygonLayer.remove();
      }
      polygonLayer = event.layer;
      const rawLatLngs = event.layer.getLatLngs?.()[0] ?? [];
      const coords = rawLatLngs.map((pt) => [pt.lat, pt.lng]);
      onPolygonCreated(event.layer, coords);
    });
  }

  return { map, polygonLayer };
}

function renderFallbackSelector(body) {
  body.append(createElement('div', {
    className: 'fallback-map-panel',
    text: 'El mapa no está disponible. Recarga la página para dibujar tu terreno.',
  }));
}
