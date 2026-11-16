// Builds the 2.5D terrain mesh from SRTM v3 (ODE 1) or Open-Meteo + Esri satellite tile.

const ELEVATION_API_URL = 'https://api.open-meteo.com/v1/elevation';
const ESRI_TILE_BASE_URL =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile';

export const VARIATION_THRESHOLD_METERS = 15;

export async function buildTerrainFromSatellite(parcel, rows = 6, cols = 8, edo1Result = null) {
  if (!parcel?.polygon?.length) {
    return createEmptyTerrain(rows, cols);
  }

  const gridPoints = buildGridCoordinates(parcel.polygon, rows, cols);

  const [elevations, cellColors] = await Promise.all([
    resolveElevations(gridPoints, parcel, edo1Result),
    sampleSatelliteTileColors(parcel.center, rows, cols),
  ]);

  const variation = computeElevationVariation(elevations, VARIATION_THRESHOLD_METERS);

  return {
    rows,
    cols,
    gridPoints,
    cellColors,
    sourceLabel: edo1Result?.cells?.length ? 'SRTM v3 + NASA POWER' : 'Satellite DEM',
    lotMeanTemp: edo1Result?.lot_mean_temp ?? null,
    ...variation,
  };
}

async function resolveElevations(gridPoints, parcel, edo1Result) {
  if (Array.isArray(edo1Result?.cells) && edo1Result.cells.length > 0) {
    return interpolateFromSrtmCells(gridPoints, edo1Result.cells);
  }
  return fetchGridElevations(gridPoints, parcel);
}

function interpolateFromSrtmCells(gridPoints, srtmCells) {
  return gridPoints.map((pt) => {
    let bestCell = srtmCells[0];
    let bestDist = Infinity;
    for (const cell of srtmCells) {
      const dLat = pt.lat - cell.latitude;
      const dLng = pt.lng - cell.longitude;
      const dist = dLat * dLat + dLng * dLng;
      if (dist < bestDist) {
        bestDist = dist;
        bestCell = cell;
      }
    }
    return Number(bestCell?.altitude_m) || 0;
  });
}

function getParcelBounds(polygon) {
  const lats = polygon.map((pt) => pt[0]);
  const lngs = polygon.map((pt) => pt[1]);
  return {
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
    minLng: Math.min(...lngs),
    maxLng: Math.max(...lngs),
  };
}

export function normalizeParcelBoundary(polygon) {
  const { minLat, maxLat, minLng, maxLng } = getParcelBounds(polygon);
  return polygon.map(([lat, lng]) => ({
    x: (lng - minLng) / (maxLng - minLng || 1),
    y: (maxLat - lat) / (maxLat - minLat || 1),
  }));
}

function buildGridCoordinates(polygon, rows, cols) {
  const { minLat, maxLat, minLng, maxLng } = getParcelBounds(polygon);

  const points = [];
  for (let r = 0; r < rows; r++) {
    const rowRatio = (r + 0.5) / rows;
    const lat = maxLat - rowRatio * (maxLat - minLat);
    for (let c = 0; c < cols; c++) {
      const colRatio = (c + 0.5) / cols;
      const lng = minLng + colRatio * (maxLng - minLng);
      points.push({
        row: r,
        col: c,
        lat,
        lng,
        insidePolygon: isPointInPolygon([lat, lng], polygon),
      });
    }
  }
  return points;
}

async function fetchGridElevations(gridPoints, parcel) {
  const lats = gridPoints.map((p) => p.lat.toFixed(5)).join(',');
  const lngs = gridPoints.map((p) => p.lng.toFixed(5)).join(',');
  const url = `${ELEVATION_API_URL}?latitude=${lats}&longitude=${lngs}`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!response.ok) {
      return buildFallbackElevations(gridPoints, parcel);
    }

    const data = await response.json();
    if (!Array.isArray(data?.elevation) || data.elevation.length !== gridPoints.length) {
      return buildFallbackElevations(gridPoints, parcel);
    }

    return data.elevation.map((val) => Number(val) || 0);
  } catch {
    return buildFallbackElevations(gridPoints, parcel);
  }
}

function buildFallbackElevations(gridPoints, parcel) {
  const baseElevation = parcel.baseElevationM ?? 3250;
  const slopeProfile = parcel.reliefDeltaM ?? computeSpanSlopeMeters(gridPoints);

  return gridPoints.map((pt) => {
    if (slopeProfile < VARIATION_THRESHOLD_METERS) {
      return baseElevation;
    }
    const normalizedRow = pt.row / 5;
    const normalizedCol = pt.col / 7;
    const stepZone = normalizedCol > 0.45 && normalizedRow < 0.65 ? 0.65 : 0.25 * normalizedCol;
    return baseElevation + Math.round(slopeProfile * stepZone);
  });
}

function computeSpanSlopeMeters(gridPoints) {
  if (!gridPoints.length) return 0;
  const lats = gridPoints.map((p) => p.lat);
  const lngs = gridPoints.map((p) => p.lng);
  const latSpan = Math.max(...lats) - Math.min(...lats);
  const lngSpan = Math.max(...lngs) - Math.min(...lngs);
  return Math.round((latSpan + lngSpan) * 4200);
}

// Only generate visual relief when elevation variation across cells exceeds the physical threshold.
export function computeElevationVariation(elevations, thresholdMeters = VARIATION_THRESHOLD_METERS) {
  if (!elevations?.length) {
    return {
      hasVariation: false,
      minElevation: 0,
      maxElevation: 0,
      deltaMeters: 0,
      normalizedHeights: [],
    };
  }

  const minElevation = Math.min(...elevations);
  const maxElevation = Math.max(...elevations);
  const deltaMeters = Number((maxElevation - minElevation).toFixed(1));
  const hasVariation = deltaMeters >= thresholdMeters;

  const normalizedHeights = elevations.map((elev) => {
    if (!hasVariation) return 0;
    const ratio = (elev - minElevation) / Math.max(deltaMeters, 1);
    return Number((ratio * 0.28).toFixed(3));
  });

  return {
    hasVariation,
    minElevation: Math.round(minElevation),
    maxElevation: Math.round(maxElevation),
    deltaMeters,
    normalizedHeights,
  };
}

async function sampleSatelliteTileColors(center, rows, cols) {
  const zoom = 16;
  const { x, y } = latLngToTileXY(center[0], center[1], zoom);
  const tileUrl = `${ESRI_TILE_BASE_URL}/${zoom}/${y}/${x}`;

  try {
    const img = await loadTileImage(tileUrl);
    const canvas = document.createElement('canvas');
    canvas.width = cols;
    canvas.height = rows;
    const ctx = canvas.getContext('2d');
    if (!ctx) return buildDefaultCellColors(rows, cols);

    ctx.drawImage(img, 64, 64, 128, 128, 0, 0, cols, rows);
    const pixels = ctx.getImageData(0, 0, cols, rows).data;
    const colors = [];

    for (let i = 0; i < pixels.length; i += 4) {
      colors.push(`rgb(${pixels[i]}, ${pixels[i + 1]}, ${pixels[i + 2]})`);
    }
    return colors;
  } catch {
    return buildDefaultCellColors(rows, cols);
  }
}

function loadTileImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    const timer = setTimeout(() => reject(new Error('Tile timeout')), 2500);
    img.onload = () => {
      clearTimeout(timer);
      resolve(img);
    };
    img.onerror = (err) => {
      clearTimeout(timer);
      reject(err);
    };
    img.src = url;
  });
}

function latLngToTileXY(lat, lng, zoom) {
  const n = 2 ** zoom;
  const latRad = (lat * Math.PI) / 180;
  const x = Math.floor(((lng + 180) / 360) * n);
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  );
  return { x, y };
}

function buildDefaultCellColors(rows, cols) {
  const total = rows * cols;
  return Array.from({ length: total }, (_, idx) =>
    idx % 2 === 0 ? '#314e34' : '#365639'
  );
}

function isPointInPolygon(point, polygon) {
  const [lat, lng] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [latI, lngI] = polygon[i];
    const [latJ, lngJ] = polygon[j];
    const intersects =
      lngI > lng !== lngJ > lng &&
      lat < ((latJ - latI) * (lng - lngI)) / (lngJ - lngI + 1e-12) + latI;
    if (intersects) inside = !inside;
  }
  return inside;
}

function createEmptyTerrain(rows, cols) {
  return {
    rows,
    cols,
    gridPoints: [],
    cellColors: buildDefaultCellColors(rows, cols),
    hasVariation: false,
    minElevation: 0,
    maxElevation: 0,
    deltaMeters: 0,
    normalizedHeights: new Array(rows * cols).fill(0),
  };
}
