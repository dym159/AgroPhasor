import { fetchRotation } from '../services/agroApi.js';
import { createElement } from '../utils/dom.js';
import { formatPhaseDate } from '../utils/phaseDates.js';

const PILOT_CROPS = [
  ['papa', 'Papa'], ['maiz', 'Maíz amiláceo'], ['frijol', 'Frijol grano seco'],
];
const amount = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 });
const day = new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium', timeZone: 'UTC' });
const text = (tag, value) => createElement(tag, { text: value });

function select(options, attrs = {}) {
  return createElement('select', { attrs }, options.map(([value, label]) =>
    createElement('option', { attrs: { value }, text: label })));
}

function field(title, control) {
  return createElement('label', {}, [text('span', title), control]);
}

function displayRoute(route, transition, title) {
  const summary = [`${route.days} días`, `${amount.format(route.dry_stress * 100)} % de déficit ambiental medio (escenario seco)`,
    `${amount.format(route.soil_loss_mm)} mm de suelo perdido`, `${amount.format(route.irrigation_mm)} mm de riego aplicado`,
    `${amount.format(route.final_water_pct)} % de humedad al final`];
  if (route.margin_pen_ha != null) summary.push(`Margen S/ ${amount.format(route.margin_pen_ha)}/ha`);
  else if (route.revenue_pen_ha != null) summary.push(`Ingreso bruto S/ ${amount.format(route.revenue_pen_ha)}/ha`);
  if (route.uncertainty) summary.push(`Viable en ${route.uncertainty.viable_samples} de ${route.uncertainty.samples} escenarios sintéticos`);
  const stages = route.stages.map((stage, index) => createElement('li', {}, [
    text('strong', stage.crop),
    text('span', `${day.format(new Date(stage.start))} → ${day.format(new Date(stage.harvest))} · ${stage.duration_days} días`),
    ...(index ? [text('span', `Preparación previa: ${transition} días`)] : []),
    createElement('details', {}, [
      text('summary', 'Ver estimaciones'),
      text('p', `Cosecha: ${amount.format(stage.yield_t_ha)} t/ha · Escenario seco: ${amount.format(stage.dry_yield_t_ha)} t/ha y ${stage.dry_stress_days} días de estrés.`),
      text('p', `Raíces: ${stage.root_depth_mm} mm · Agotamiento permisible: ${amount.format(stage.depletion_fraction * 100)} %.`),
      text('p', stage.price_pen_kg == null ? 'Precio regional sin datos.' :
        `Precio en chacra: S/ ${amount.format(stage.price_pen_kg)}/kg.`),
    ]),
  ]));
  return createElement('details', { attrs: title === 'Recomendada' ? { open: '' } : {} }, [
    text('summary', title), text('p', summary.join(' · ')), createElement('ol', {}, stages),
  ]);
}

export function createRotationsPanel(container, onApply) {
  if (!container) return { update: () => {} };
  const count = select([['3', '3 cultivos'], ['2', '2 cultivos'], ['4', '4 cultivos'], ['5', '5 cultivos'], ['6', '6 cultivos']]);
  const region = createElement('input', { type: 'text', attrs: { placeholder: 'Ej. Junín', maxlength: 100 } });
  const irrigation = createElement('input', { type: 'number', attrs: { value: 0, min: 0, max: 30, step: 'any', required: '' } });
  const residue = createElement('input', { type: 'number', attrs: { value: 50, min: 0, max: 100, required: '' } });
  const irrigationCost = createElement('input', { type: 'number', attrs: { value: 0, min: 0, max: 10000, step: 'any', required: '' } });
  const uncertainty = createElement('input', { type: 'checkbox' });
  const costInputs = PILOT_CROPS.map(([id, label]) => [id, label,
    createElement('input', { type: 'number', attrs: { min: 0, max: 1000000, step: 'any' } })]);
  const retry = createElement('button', { type: 'button', className: 'btn', text: 'Reintentar' });
  retry.hidden = true;
  const planting = createElement('p', { className: 'rotation-planting' });
  const status = createElement('p', { attrs: { role: 'status' } });
  const result = createElement('section', { className: 'rotation-recommendation' });
  const form = createElement('form', { className: 'rotation-form' }, [
    createElement('details', {}, [text('summary', 'Ajustes de rotación'),
      field('Longitud de la rotación', count),
      field('Región para precios en chacra', region), field('Riego durante cultivo (mm/día)', irrigation),
      field('Rastrojo conservado (%)', residue),
      field('Evaluar 20 escenarios de incertidumbre', uncertainty),
      field('Costo de riego (S/ por mm y ha)', irrigationCost),
      text('p', 'Costos por hectárea (opcional)'),
      ...costInputs.map(([, label, input]) => field(`${label} (S/ha)`, input))]),
  ]);
  container.replaceChildren(
    createElement('div', { className: 'panel-header' }, [
      createElement('h2', { className: 'panel-title', text: 'Rotación recomendada' }),
    ]),
    createElement('div', { className: 'rotations-list panel-scroll' }, [planting, status, retry, result, form])
  );

  let state, controller, timer;
  let lastSignature = '';
  const cancel = () => { clearTimeout(timer); controller?.abort(); };

  function calculate({ force = false } = {}) {
    const first = state.phases[0];
    const cropId = first?.cropId || state.previewCropId || 'papa';
    const startDate = first?.start ?? state.plantingStart;
    const name = PILOT_CROPS.find(([id]) => id === cropId)?.[1];
    const center = state.selectedParcel?.center;
    const message = !center ? 'Selecciona una parcela para calcular la rotación.'
      : !name ? 'La rotación automática está disponible para papa, maíz amiláceo y frijol seco.'
      : !form.checkValidity() ? 'Revisa los valores en Ajustes de rotación.'
      : '';
    planting.textContent = center && name ? `${name} · Siembra ${formatPhaseDate(startDate)}` : '';
    const validSlopes = state.parcelSimulationResult?.cells.map((cell) => cell.slope_deg)
      .filter(Number.isFinite) ?? [];
    const slope = validSlopes.length
      ? Math.min(80, validSlopes.reduce((total, value) => total + value, 0) / validSlopes.length)
      : undefined;
    const input = {
      crop_id: cropId, start_date: startDate, crop_count: Number(count.value),
      baseline_phases: state.phases.length >= 2 && state.phases.length <= 6 &&
        state.phases.every((phase) => phase.cropId && phase.harvest) ? state.phases : undefined,
      terrain_cells: state.parcelSimulationResult?.cells.map((cell) => ({
        area_m2: cell.area_m2, altitude_m: cell.altitude_m, slope_deg: Math.min(80, cell.slope_deg),
      })),
      latitude: center?.[0], longitude: center?.[1], slope_deg: slope, weights: state.knobs,
      region: region.value.trim(), irrigation_mm_day: irrigation.valueAsNumber,
      evaluate_uncertainty: uncertainty.checked,
      residue_fraction: residue.valueAsNumber / 100, irrigation_cost_pen_mm_ha: irrigationCost.valueAsNumber,
      costs_pen_ha: Object.fromEntries(costInputs.filter(([, , input]) => input.value !== '')
        .map(([id, , input]) => [id, input.valueAsNumber])),
    };
    const signature = message || JSON.stringify([state.selectedParcel.id, input]);
    if (!force && signature === lastSignature) return;
    lastSignature = signature;
    cancel();
    retry.hidden = true;
    result.replaceChildren();
    status.textContent = message || 'Calculando la rotación…';
    if (message) return;
    const current = new AbortController();
    controller = current;
    timer = setTimeout(async () => {
      try {
        const data = await fetchRotation(input, current.signal);
        if (current.signal.aborted) return;
        status.textContent = data.routes.length
          ? 'Las rutas se ordenaron según tus perillas.'
          : data.rejected?.length ? 'Las rutas evaluadas exceden los límites térmicos de los cultivos.'
          : 'Los criterios elegidos no se pueden evaluar con los datos disponibles.';
        const notes = [
          `Clima histórico NASA POWER ${data.climate_year}. Escenario seco: ${amount.format((1 - data.dry_rain_factor) * 100)} % menos lluvia.`,
          'Suelo inicial y densidad aparente de referencia (1,3 t/m³). Ciclos y parámetros del catálogo pendientes de calibración local.',
          ...(data.uncertainty_assumptions ? [data.uncertainty_assumptions] : []),
          ...(data.slope_assumed ? ['Pendiente de referencia: 0° (sin dato de relieve).'] : []),
          ...(data.economic_metric === 'revenue' ? ['El criterio económico usa ingreso bruto por falta de costos completos.'] : []),
          ...(data.economic_metric === 'unavailable' ? ['Faltan precios regionales comparables. El criterio económico queda fuera del ranking.'] : []),
        ];
        result.replaceChildren(
          ...(data.baseline ? [displayRoute(data.baseline, data.transition_days, 'Tu rotación actual')] : []),
          ...(data.baseline_rejected ? [text('p', 'Tu rotación actual incumple los límites térmicos o la alternancia de familias.')] : []),
          ...(data.rejected?.length ? [text('p', `${data.rejected.length} continuaciones descartadas por riesgo térmico.`)] : []),
          ...data.routes.map((route, index) => displayRoute(route, data.transition_days,
            index === 0 ? 'Recomendada' : `Alternativa ${index}`)),
          ...(data.routes.length ? [createElement('button', {
            type: 'button', className: 'btn', text: 'Aplicar a la línea de tiempo',
            onClick: () => {
              if (state.phases.length && !window.confirm('¿Reemplazar las fases de la línea de tiempo con la rotación recomendada?')) return;
              onApply(data.routes[0].stages);
            },
          })] : []),
          createElement('details', {}, [
            text('summary', 'Datos y alcance'),
            ...notes.map((note) => text('p', note)),
            createElement('p', {}, [
              createElement('a', { text: 'Rotación andina (INIA)', attrs: {
                href: 'https://repositorio.inia.gob.pe/handle/20.500.12955/1146',
              } }),
              ' · ',
              createElement('a', { text: 'Campañas de siembra (MIDAGRI)', attrs: {
                href: 'https://www.gob.pe/institucion/midagri/informes-publicaciones/7220015-marco-orientador-de-cultivos',
              } }),
            ]),
          ]),
        );
      } catch (error) {
        if (current.signal.aborted) return;
        status.textContent = error.message;
        retry.hidden = false;
      }
    }, 250);
  }

  form.addEventListener('submit', (event) => event.preventDefault());
  form.addEventListener('input', () => calculate());
  retry.addEventListener('click', () => calculate({ force: true }));

  return {
    update(next) {
      state = next;
      calculate();
    },
  };
}
