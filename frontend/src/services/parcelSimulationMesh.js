// Visual scaling exaggerates topsoil loss in mm relative to SRTM relief in meters.
const SINK_PER_MM = 0.0006;

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
    const polygons = type === 'MultiPolygon'
      ? coordinates
      : type === 'Polygon' ? [coordinates] : [[parcel.polygon.map(([lat, lon]) => [lon, lat])]];
    return {
      cell,
      center: position([cell.longitude, cell.latitude]),
      polygons: polygons.map((rings) => rings.map((ring) => ring.map(position))),
      z: (cell.altitude_m - minElevation) * elevationScale - cell.accumulated_erosion_mm * SINK_PER_MM,
      color: `rgb(${cell.soil_color_rgb.join(',')})`,
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
