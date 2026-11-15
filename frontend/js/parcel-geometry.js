// Coordenadas mundiales Web Mercator, iguales a las del mapa Leaflet.
export function projectCoordinate([lng, lat]) {
  const sin = Math.sin(Math.max(-85.05112878, Math.min(85.05112878, lat)) * Math.PI / 180);
  return [(lng + 180) / 360 * 256,
    (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * 256];
}

export function parcelFootprint(geometry) {
  const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates]
    : geometry?.type === 'MultiPolygon' ? geometry.coordinates : [];
  const projected = polygons.map(polygon => polygon.map(ring => ring.map(projectCoordinate)));
  const points = projected.flat(2);
  if (!points.length) return null;
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const width = Math.max(...xs) - minX, height = Math.max(...ys) - minY;
  if (!(width > 0 && height > 0)) return null;
  const scale = Math.min(190 / width, 130 / height);
  const offsetX = (190 - width * scale) / 2, offsetY = (130 - height * scale) / 2;
  return {
    polygons: projected.map(p => p.map(r => r.map(([x, y]) =>
      [offsetX + (x - minX) * scale, offsetY + (y - minY) * scale]))),
    minX, minY, width, height, scale, offsetX, offsetY
  };
}
