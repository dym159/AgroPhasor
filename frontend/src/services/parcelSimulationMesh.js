// La escala visual exagera el desgaste en mm respecto al desnivel SRTM en m.
const SINK_PER_MM = 0.0006;
const RAIN_SINK_PER_MM = 0.0012;

export function lissajousShieldScore(lissajousArea, psi = null, aLRef = 2.0, omegaL = 0.65) {
  const area = Math.max(0, Number(lissajousArea) || 0);
  const ref = Math.max(1e-4, Number(aLRef) || 2.0);
  const etaL = area / (area + ref);
  if (psi === null || psi === undefined) return Math.max(0, Math.min(1, etaL));
  const wL = Math.max(0, Math.min(1, Number(omegaL) || 0.65));
  const psiClamped = Math.max(0, Math.min(1, Number(psi) || 0));
  return Math.max(0, Math.min(1, wL * etaL + (1 - wL) * psiClamped));
}

export function soilColorRgb({
  retentionRatio = 1,
  etaNutrientes = null,
  waterSaturation = null,
  omegaNutrientes = 0.55,
  omegaHumedad = 0.45,
} = {}) {
  const hRatio = Math.max(0, Math.min(1, Number(retentionRatio)));
  let vitality = hRatio;
  if (etaNutrientes !== null || waterSaturation !== null) {
    const nut = Math.max(0, Math.min(1, Number(etaNutrientes ?? 1)));
    const hum = Math.max(0, Math.min(1, Number(waterSaturation ?? 1)));
    const sumW = Math.max(1e-6, omegaNutrientes + omegaHumedad);
    vitality = hRatio * ((omegaNutrientes / sumW) * nut + (omegaHumedad / sumW) * hum);
  }
  const brown = [101, 67, 33];
  const gray = [128, 128, 128];
  return gray.map((g, i) => Math.round(g + (brown[i] - g) * vitality));
}

function polygonCentroid(ring) {
  if (!ring || ring.length < 3) return ring?.[0] ?? [0, 0];
  let area = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[i + 1];
    const cross = x0 * y1 - x1 * y0;
    area += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  if (Math.abs(area) < 1e-9) {
    const pts = ring.slice(0, -1);
    return [
      pts.reduce((s, [x]) => s + x, 0) / Math.max(1, pts.length),
      pts.reduce((s, [, y]) => s + y, 0) / Math.max(1, pts.length),
    ];
  }
  return [cx / (3 * area), cy / (3 * area)];
}

export function buildParcelSimulationMesh(parcel, cells) {
  const lats = parcel.polygon.map(([lat]) => lat);
  const lons = parcel.polygon.map(([, lon]) => lon);
  const [south, north] = [Math.min(...lats), Math.max(...lats)];
  const [west, east] = [Math.min(...lons), Math.max(...lons)];
  const midLat = (south + north) / 2;
  const midLon = (west + east) / 2;
  const lonRatio = Math.cos(midLat * Math.PI / 180);
  const scale = 1.8 / Math.max((east - west) * lonRatio, north - south);
  const position = ([lon, lat]) => [
    (lon - midLon) * lonRatio * scale,
    (midLat - lat) * scale,
  ];

  const elevations = cells.map((cell) => cell.altitude_m);
  const minElevation = Math.min(...elevations);
  const relief = Math.max(...elevations) - minElevation;
  const elevationScale = 0.28 / Math.max(15, relief);
  const meshCells = cells.map((cell) => {
    const { type, coordinates } = cell.geometry;
    const rawPolygons = type === 'MultiPolygon'
      ? coordinates
      : type === 'Polygon' ? [coordinates] : [[parcel.polygon.map(([lat, lon]) => [lon, lat])]];
    const projectedPolygons = rawPolygons.map((rings) => rings.map((ring) => ring.map(position)));
    const outerRing = projectedPolygons[0]?.[0];
    const center = outerRing?.length >= 3
      ? polygonCentroid(outerRing)
      : position([cell.longitude, cell.latitude]);
    const rgb = cell.soil_color_rgb ?? soilColorRgb({
      retentionRatio: cell.soil_retention_ratio ?? 1,
      etaNutrientes: cell.eta_nutrientes ?? null,
      waterSaturation: cell.water_condition_index ?? null,
    });
    const rainDropMm = Number(cell.rain_height_variation_mm) || 0;
    return {
      cell,
      center,
      polygons: projectedPolygons,
      z: (cell.altitude_m - minElevation) * elevationScale
        - (cell.accumulated_erosion_mm ?? 0) * SINK_PER_MM
        - rainDropMm * RAIN_SINK_PER_MM,
      color: `rgb(${rgb.join(',')})`,
    };
  });
  return {
    cells: meshCells,
    floor: Math.min(0, ...meshCells.map(({ z }) => z)) - 0.12,
  };
}

export function buildPreviewMesh(model) {
  const { rows, cols, gridPoints, cellColors, normalizedHeights } = model;
  const vertices = (col, row) => [(2 * col / cols - 1) * 0.9, (2 * row / rows - 1) * 0.65];
  return {
    floor: -0.12,
    cells: gridPoints.flatMap(({ insidePolygon, row, col }, index) => insidePolygon ? [{
      center: vertices(col + 0.5, row + 0.5),
      polygons: [[[
        vertices(col, row), vertices(col + 1, row),
        vertices(col + 1, row + 1), vertices(col, row + 1),
      ]]],
      z: normalizedHeights[index],
      color: cellColors[index],
    }] : []),
  };
}

export function shieldColor(index) {
  const red = [249, 64, 70];
  const blue = [42, 155, 255];
  return `rgb(${red.map((channel, i) => Math.round(channel + (blue[i] - channel) * index)).join(',')})`;
}
