const COMPACT_CROP_ROWS = [
  'papa|Papa Nativa|Tubérculos|#4ade80',
  'maiz|Maíz Amiláceo|Granos|#facc15',
  'quinua|Quinua|Granos|#fb923c',
  'haba|Haba|Leguminosas|#22c55e',
  'frijol|Frijol grano seco|Leguminosas|#4ade80',
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

export const VISUAL_CROPS = buildCropCatalog(COMPACT_CROP_ROWS).filter((crop) => ['papa', 'maiz', 'frijol'].includes(crop.id));
export const CROP_DRAG_TYPE = 'application/x-agrophasor-crop';

export const CROP_GROUPS = ['Todos', ...new Set(VISUAL_CROPS.map((crop) => crop.group))];

export const STRATEGY_MODES = [
  {
    id: 'max-yield',
    backendMode: 'mayor_ganancia',
    weights: { w1: 5, w2: 5, w3: 85, w4: 5 },
    label: 'Máximo Rendimiento',
    accentColor: '#f59e0b',
    subRoutes: [
      { id: 'fast-cycle', label: 'Rotación rápida', weights: { w1: 15, w2: 15, w3: 30, w4: 40 } },
      { id: 'yield-balance', label: 'Equilibrio', weights: { w1: 20, w2: 20, w3: 35, w4: 25 } },
      { id: 'max-profit', label: 'Mayor ganancia', weights: { w1: 10, w2: 15, w3: 50, w4: 25 } },
    ],
  },
  {
    id: 'optimal-balance',
    backendMode: 'balance_optimo',
    weights: { w1: 25, w2: 25, w3: 25, w4: 25 },
    label: 'Balance Óptimo',
    accentColor: '#38bdf8',
    subRoutes: [
      { id: 'global-pareto', label: 'Compromiso global', weights: { w1: 25, w2: 25, w3: 25, w4: 25 } },
    ],
  },
  {
    id: 'max-resilience',
    backendMode: 'maxima_resiliencia',
    weights: { w1: 50, w2: 30, w3: 10, w4: 10 },
    label: 'Máxima Resiliencia',
    accentColor: '#22c55e',
    subRoutes: [
      { id: 'water-austerity', label: 'Austeridad hídrica', weights: { w1: 50, w2: 25, w3: 10, w4: 15 } },
      { id: 'resilience-balance', label: 'Equilibrio', weights: { w1: 35, w2: 35, w3: 15, w4: 15 } },
      { id: 'best-soil', label: 'Mejor tierra', weights: { w1: 25, w2: 50, w3: 10, w4: 15 } },
    ],
  },
];

export const PDF_KNOBS = [
  { id: 'w1', symbol: 'w1', label: 'Austeridad Hídrica', defaultValue: 25 },
  { id: 'w2', symbol: 'w2', label: 'Mejor Tierra al Final', defaultValue: 25 },
  { id: 'w3', symbol: 'w3', label: 'Mayor Ganancia', defaultValue: 25 },
  { id: 'w4', symbol: 'w4', label: 'Rotación Más Rápida', defaultValue: 25 },
];

export const TIMELINE_MONTHS = [
  'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
];
