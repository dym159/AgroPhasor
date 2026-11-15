const COMPACT_CROP_ROWS = [
  'papa|Papa Nativa|Tubérculos|#4ade80',
  'maiz|Maíz Amiláceo|Granos|#facc15',
  'quinua|Quinua|Granos|#fb923c',
  'haba|Haba|Leguminosas|#22c55e',
  'alfalfa|Alfalfa|Forrajes|#10b981',
  'avena|Avena Forrajera|Forrajes|#34d399',
  'cebada|Cebada|Granos|#a3e635',
  'tomate|Tomate|Hortalizas|#f87171',
  'oca|Oca Andina|Tubérculos|#c084fc',
  'tarwi|Tarwi|Leguminosas|#38bdf8',
  'trigo|Trigo|Granos|#fbbf24',
  'arveja|Arveja|Leguminosas|#4ade80',
];

function buildCropCatalog(rows) {
  return rows.map((row) => {
    const [id, name, group, tint] = row.split('|');
    return { id, name, group, tint };
  });
}

export const VISUAL_CROPS = buildCropCatalog(COMPACT_CROP_ROWS);

export const CROP_GROUPS = ['Todos', ...new Set(VISUAL_CROPS.map((crop) => crop.group))];

export const DEMO_PARCELS = [
  {
    id: 'mantaro-base',
    name: 'Valle del Mantaro (Plano)',
    baseElevationM: 3250,
    reliefDeltaM: 2,
    center: [-12.06, -75.21],
    polygon: [
      [-12.0595, -75.2108],
      [-12.0595, -75.2096],
      [-12.0604, -75.2096],
      [-12.0604, -75.2108],
    ],
  },
  {
    id: 'ica-sur',
    name: 'Valle de Ica (Plano)',
    baseElevationM: 406,
    reliefDeltaM: 1,
    center: [-14.07, -75.73],
    polygon: [
      [-14.0695, -75.7308],
      [-14.0695, -75.7295],
      [-14.0705, -75.7295],
      [-14.0705, -75.7308],
    ],
  },
  {
    id: 'ladera-2z',
    name: 'Ladera Andina (Con pendiente)',
    baseElevationM: 3380,
    reliefDeltaM: 36,
    center: [-12.0359, -75.1745],
    polygon: [
      [-12.035, -75.1755],
      [-12.035, -75.1735],
      [-12.0368, -75.1735],
      [-12.0368, -75.1755],
    ],
  },
];

export const STRATEGY_MODES = [
  {
    id: 'max-yield',
    backendMode: 'mayor_ganancia',
    label: 'Máximo Rendimiento',
    accentColor: '#f59e0b',
    defaultKnobs: { w1: 15, w2: 15, w3: 45, w4: 25 },
    subRoutes: [
      { id: 'fast-cycle', label: 'Rotación rápida', knobs: { w1: 15, w2: 15, w3: 30, w4: 40 }, rotationId: 'agil-ciclo-corto' },
      { id: 'yield-balance', label: 'Equilibrio', knobs: { w1: 20, w2: 20, w3: 35, w4: 25 }, rotationId: 'forrajera-mixta' },
      { id: 'max-profit', label: 'Mayor ganancia', knobs: { w1: 10, w2: 15, w3: 50, w4: 25 }, rotationId: 'comercial-intensiva' },
    ],
  },
  {
    id: 'optimal-balance',
    backendMode: 'balance_optimo',
    label: 'Balance Óptimo',
    accentColor: '#38bdf8',
    defaultKnobs: { w1: 25, w2: 25, w3: 25, w4: 25 },
    subRoutes: [
      { id: 'global-pareto', label: 'Compromiso global', knobs: { w1: 25, w2: 25, w3: 25, w4: 25 }, rotationId: 'zonificada-25d' },
    ],
  },
  {
    id: 'max-resilience',
    backendMode: 'maxima_resiliencia',
    label: 'Máxima Resiliencia',
    accentColor: '#22c55e',
    defaultKnobs: { w1: 40, w2: 35, w3: 10, w4: 15 },
    subRoutes: [
      { id: 'water-austerity', label: 'Austeridad hídrica', knobs: { w1: 50, w2: 25, w3: 10, w4: 15 }, rotationId: 'austeridad-hidrica' },
      { id: 'resilience-balance', label: 'Equilibrio', knobs: { w1: 35, w2: 35, w3: 15, w4: 15 }, rotationId: 'zonificada-25d' },
      { id: 'best-soil', label: 'Mejor tierra', knobs: { w1: 25, w2: 50, w3: 10, w4: 15 }, rotationId: 'hospital-suelo' },
    ],
  },
];

export const PDF_KNOBS = [
  { id: 'w1', symbol: 'w1', label: 'Austeridad Hídrica', defaultValue: 25 },
  { id: 'w2', symbol: 'w2', label: 'Mejor Tierra al Final', defaultValue: 25 },
  { id: 'w3', symbol: 'w3', label: 'Mayor Ganancia', defaultValue: 25 },
  { id: 'w4', symbol: 'w4', label: 'Rotación Más Rápida', defaultValue: 25 },
];

export const ROTATION_TYPES = [
  { id: 'austeridad-hidrica', name: 'Austeridad Hídrica', backendRoute: 'quinua_habas_avena' },
  { id: 'hospital-suelo', name: 'Hospital de Suelo', backendRoute: 'papa_habas_quinua' },
  { id: 'zonificada-25d', name: 'Zonificada 2.5D', backendRoute: 'papa_habas_quinua' },
  { id: 'forrajera-mixta', name: 'Forrajera / Mixta', backendRoute: 'maiz_habas_papa' },
  { id: 'agil-ciclo-corto', name: 'Ágil / Ciclo Corto', backendRoute: 'quinua_habas_avena' },
  { id: 'comercial-intensiva', name: 'Comercial Intensiva', backendRoute: 'maiz_habas_papa' },
];

export const TIMELINE_MONTHS = [
  'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
];
