const COMPACT_CROP_ROWS = [
  'papa|Native Potato|Tubers|#4ade80',
  'maiz|Amylaceous Maize|Grains|#facc15',
  'quinua|Quinoa|Grains|#fb923c',
  'haba|Fava Bean|Legumes|#22c55e',
  'frijol|Dry Bean|Legumes|#4ade80',
  'alfalfa|Alfalfa|Forage|#10b981',
  'avena|Forage Oat|Forage|#34d399',
  'cebada|Barley|Grains|#a3e635',
  'tomate|Tomato|Vegetables|#f87171',
  'oca|Andean Oca|Tubers|#c084fc',
  'tarwi|Tarwi (Andean Lupin)|Legumes|#38bdf8',
  'trigo|Wheat|Grains|#fbbf24',
  'arveja|Pea|Legumes|#4ade80',
];

function buildCropCatalog(rows) {
  return rows.map((row) => {
    const [id, name, group, tint] = row.split('|');
    return { id, name, group, tint };
  });
}

export const VISUAL_CROPS = buildCropCatalog(COMPACT_CROP_ROWS).filter((crop) => ['papa', 'maiz', 'frijol'].includes(crop.id));
export const CROP_DRAG_TYPE = 'application/x-agrophasor-crop';

export const CROP_GROUPS = ['All', ...new Set(VISUAL_CROPS.map((crop) => crop.group))];

export const STRATEGY_MODES = [
  {
    id: 'max-yield',
    backendMode: 'mayor_ganancia',
    weights: { w1: 5, w2: 5, w3: 85, w4: 5 },
    label: 'Maximum Yield',
    accentColor: '#f59e0b',
    subRoutes: [
      { id: 'fast-cycle', label: 'Fast rotation', weights: { w1: 15, w2: 15, w3: 30, w4: 40 } },
      { id: 'yield-balance', label: 'Balanced yield', weights: { w1: 20, w2: 20, w3: 35, w4: 25 } },
      { id: 'max-profit', label: 'Highest profit', weights: { w1: 10, w2: 15, w3: 50, w4: 25 } },
    ],
  },
  {
    id: 'optimal-balance',
    backendMode: 'balance_optimo',
    weights: { w1: 25, w2: 25, w3: 25, w4: 25 },
    label: 'Optimal Balance',
    accentColor: '#38bdf8',
    subRoutes: [
      { id: 'global-pareto', label: 'Global compromise', weights: { w1: 25, w2: 25, w3: 25, w4: 25 } },
    ],
  },
  {
    id: 'max-resilience',
    backendMode: 'maxima_resiliencia',
    weights: { w1: 50, w2: 30, w3: 10, w4: 10 },
    label: 'Maximum Resilience',
    accentColor: '#22c55e',
    subRoutes: [
      { id: 'water-austerity', label: 'Water austerity', weights: { w1: 50, w2: 25, w3: 10, w4: 15 } },
      { id: 'resilience-balance', label: 'Balanced resilience', weights: { w1: 35, w2: 35, w3: 15, w4: 15 } },
      { id: 'best-soil', label: 'Best soil', weights: { w1: 25, w2: 50, w3: 10, w4: 15 } },
    ],
  },
];

export const PDF_KNOBS = [
  { id: 'w1', symbol: 'w1', label: 'Water Austerity', defaultValue: 25 },
  { id: 'w2', symbol: 'w2', label: 'Best Final Soil', defaultValue: 25 },
  { id: 'w3', symbol: 'w3', label: 'Highest Profit', defaultValue: 25 },
  { id: 'w4', symbol: 'w4', label: 'Fastest Rotation', defaultValue: 25 },
];

export const TIMELINE_MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];
