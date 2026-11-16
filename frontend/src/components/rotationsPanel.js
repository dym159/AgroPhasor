import { fetchRotation } from '../services/agroApi.js';
import { createElement } from '../utils/dom.js';
import { formatPhaseDate } from '../utils/phaseDates.js';
import { rankCandidates } from '../utils/rotationRanking.js';

const PILOT_CROPS = [
  ['papa', 'Native Potato'], ['maiz', 'Amylaceous Maize'], ['frijol', 'Dry Bean'],
];
const MIDAGRI_REGIONS = [
  'Amazonas', 'Ancash', 'Apurímac', 'Arequipa', 'Ayacucho', 'Cajamarca', 'Cusco',
  'Huancavelica', 'Huánuco', 'Ica', 'Junín', 'La Libertad', 'Lambayeque', 'Lima',
  'Lima Metropolitana', 'Loreto', 'Madre de Dios', 'Moquegua', 'Pasco', 'Piura',
  'Puno', 'San Martín', 'Tacna', 'Tumbes', 'Ucayali',
];
const amount = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
const day = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeZone: 'UTC' });
const text = (tag, value) => createElement(tag, { text: value });

function select(options, attrs = {}) {
  return createElement('select', { attrs }, options.map(([value, label]) =>
    createElement('option', { attrs: { value }, text: label })));
}

function field(title, control) {
  return createElement('label', {}, [text('span', title), control]);
}

function displayRoute(route, transition, title) {
  const sequence = route.stages.map((stage) => stage.crop).join(' → ');
  const summaryTitle = sequence ? `${title} · ${sequence}` : title;
  const summary = [`${route.days} days`, `${amount.format(route.dry_stress * 100)}% mean environmental deficit (dry scenario)`,
    `${amount.format(route.soil_loss_mm)} mm soil loss`, `${amount.format(route.irrigation_mm)} mm irrigation applied`,
    `${amount.format(route.final_water_pct)}% final soil moisture`];
  if (route.margin_pen_ha != null) summary.push(`Margin S/ ${amount.format(route.margin_pen_ha)}/ha`);
  else if (route.revenue_pen_ha != null) summary.push(`Gross revenue S/ ${amount.format(route.revenue_pen_ha)}/ha`);
  if (route.uncertainty) {
    const conf = route.uncertainty.confidence_pct != null ? ` (${route.uncertainty.confidence_pct}%)` : '';
    summary.push(`Viable in ${route.uncertainty.viable_samples} of ${route.uncertainty.samples} Monte Carlo scenarios${conf}`);
  }
  const stages = route.stages.map((stage, index) => createElement('li', {}, [
    text('strong', stage.crop),
    text('span', `${day.format(new Date(stage.start))} → ${day.format(new Date(stage.harvest))} · ${stage.duration_days} days`),
    ...(index ? [text('span', `Prior transition: ${transition} days`)] : []),
    createElement('details', {}, [
      text('summary', 'View estimates'),
      text('p', `Yield: ${amount.format(stage.yield_t_ha)} t/ha · Dry scenario: ${amount.format(stage.dry_yield_t_ha)} t/ha and ${stage.dry_stress_days} stress days.`),
      text('p', `Root depth: ${stage.root_depth_mm} mm · Allowable depletion: ${amount.format(stage.depletion_fraction * 100)}%.`),
      text('p', stage.price_pen_kg == null ? 'Regional price unavailable.' :
        `Farm-gate price: S/ ${amount.format(stage.price_pen_kg)}/kg.`),
    ]),
  ]));
  return createElement('details', { attrs: title === 'Recommended' ? { open: '' } : {} }, [
    text('summary', summaryTitle), text('p', summary.join(' · ')), createElement('ol', {}, stages),
  ]);
}

export function createRotationsPanel(container, onApply) {
  if (!container) return { update: () => {} };
  const count = select([['3', '3 crops'], ['2', '2 crops'], ['4', '4 crops'], ['5', '5 crops'], ['6', '6 crops']]);
  const regionListId = 'midagri-regions';
  const regionList = createElement('datalist', { attrs: { id: regionListId } },
    MIDAGRI_REGIONS.map((name) => createElement('option', { attrs: { value: name } })));
  const region = createElement('input', {
    type: 'text',
    attrs: { value: 'Junín', placeholder: 'e.g. Junín', maxlength: 100, list: regionListId },
  });
  const irrigation = createElement('input', { type: 'number', attrs: { value: 0, min: 0, max: 30, step: 'any', required: '' } });
  const residue = createElement('input', { type: 'number', attrs: { value: 50, min: 0, max: 100, required: '' } });
  const irrigationCost = createElement('input', { type: 'number', attrs: { value: 0, min: 0, max: 10000, step: 'any', required: '' } });
  const uncertainty = createElement('input', { type: 'checkbox' });
  const costInputs = PILOT_CROPS.map(([id, label]) => [id, label,
    createElement('input', { type: 'number', attrs: { min: 0, max: 1000000, step: 'any' } })]);
  const retry = createElement('button', { type: 'button', className: 'btn', text: 'Retry' });
  retry.hidden = true;
  const planting = createElement('p', { className: 'rotation-planting' });
  const status = createElement('p', { attrs: { role: 'status' } });
  const result = createElement('section', { className: 'rotation-recommendation' });
  const form = createElement('form', { className: 'rotation-form' }, [
    createElement('details', {}, [text('summary', 'Rotation settings'),
      field('Rotation length', count),
      field('Region for farm-gate prices', region), regionList, field('Crop irrigation (mm/day)', irrigation),
      field('Retained stover residue (%)', residue),
      field('Evaluate 20 uncertainty scenarios', uncertainty),
      field('Irrigation cost (S/ per mm·ha)', irrigationCost),
      text('p', 'Production costs per hectare (optional)'),
      ...costInputs.map(([, label, input]) => field(`${label} (S/ha)`, input))]),
  ]);
  container.replaceChildren(
    createElement('div', { className: 'panel-header' }, [
      createElement('h2', { className: 'panel-title', text: 'Recommended Rotation' }),
    ]),
    createElement('div', { className: 'rotations-list panel-scroll' }, [planting, status, retry, result, form])
  );

  let state, controller, timer;
  let lastPhysicalSignature = '';
  let lastData = null;
  let lastDataSignature = '';
  let lastKnobSignature = '';
  const cancel = () => { clearTimeout(timer); controller?.abort(); };

  function renderRecommendation(data, knobs) {
    const routes = Array.isArray(data.candidates) && data.bounds
      ? rankCandidates(data.candidates, data.bounds, knobs)
      : data.routes;
    status.textContent = routes.length
      ? 'Routes ranked according to your priority knobs.'
      : data.rejected?.length ? 'Evaluated routes exceed the thermal limits of the crops.'
      : 'Selected criteria cannot be evaluated with the available data.';
    const notes = [
      data.climate_window
        ? `${data.climate_source} (fitted ${data.climate_window.start} to ${data.climate_window.end}, ${data.climate_window.days} days). Dry scenario: ${amount.format((1 - data.dry_rain_factor) * 100)}% less rainfall.`
        : `Historical NASA POWER climate ${data.climate_year}. Dry scenario: ${amount.format((1 - data.dry_rain_factor) * 100)}% less rainfall.`,
      'Reference initial soil and bulk density (1.3 t/m³). Catalog cycles and parameters pending local calibration.',
      ...(data.uncertainty_assumptions ? [data.uncertainty_assumptions] : []),
      ...(data.slope_assumed ? ['Reference slope: 0° (no relief data).'] : []),
      ...(data.economic_metric === 'revenue' ? ['Economic criterion uses gross revenue because full production costs were not provided.'] : []),
      ...(data.economic_metric === 'unavailable' ? ['Comparable regional prices are unavailable. The economic criterion is excluded from ranking.'] : []),
    ];
    result.replaceChildren(
      ...(data.baseline ? [displayRoute(data.baseline, data.transition_days, 'Your current rotation')] : []),
      ...(data.baseline_rejected ? [text('p', 'Your current rotation violates thermal limits or botanical family alternation.')] : []),
      ...(data.rejected?.length ? [text('p', `${data.rejected.length} continuations discarded due to thermal risk.`)] : []),
      ...routes.map((route, index) => displayRoute(route, data.transition_days,
        index === 0 ? 'Recommended' : `Alternative ${index}`)),
      ...(routes.length ? [createElement('button', {
        type: 'button', className: 'btn', text: 'Apply to timeline',
        onClick: () => {
          if (state.phases.length && !window.confirm('Replace current timeline phases with the recommended rotation?')) return;
          onApply(routes[0].stages);
        },
      })] : []),
      createElement('details', {}, [
        text('summary', 'Data sources & scope'),
        ...notes.map((note) => text('p', note)),
        createElement('p', {}, [
          createElement('a', { text: 'Andean crop rotation (INIA)', attrs: {
            href: 'https://repositorio.inia.gob.pe/handle/20.500.12955/1146',
          } }),
          ' · ',
          createElement('a', { text: 'Planting campaigns (MIDAGRI)', attrs: {
            href: 'https://www.gob.pe/institucion/midagri/informes-publicaciones/7220015-marco-orientador-de-cultivos',
          } }),
        ]),
      ]),
    );
  }

  function calculate({ force = false } = {}) {
    const first = state.phases[0];
    const cropId = first?.cropId || state.previewCropId || 'papa';
    const startDate = first?.start ?? state.plantingStart;
    const name = PILOT_CROPS.find(([id]) => id === cropId)?.[1];
    const center = state.selectedParcel?.center;
    const message = !center ? 'Select a parcel to calculate the crop rotation.'
      : !name ? 'Automatic rotation is available for Native Potato, Amylaceous Maize, and Dry Bean.'
      : !form.checkValidity() ? 'Check the values in Rotation settings.'
      : '';
    planting.textContent = center && name ? `${name} · Planting ${formatPhaseDate(startDate)}` : '';
    const validSlopes = state.parcelSimulationResult?.cells.map((cell) => cell.slope_deg)
      .filter(Number.isFinite) ?? [];
    const slope = validSlopes.length
      ? Math.min(80, validSlopes.reduce((total, value) => total + value, 0) / validSlopes.length)
      : undefined;
    const physicalInput = {
      crop_id: cropId, start_date: startDate, crop_count: Number(count.value),
      baseline_phases: state.phases.length >= 2 && state.phases.length <= 6 &&
        state.phases.every((phase) => phase.cropId && phase.harvest) ? state.phases : undefined,
      terrain_cells: state.parcelSimulationResult?.cells.map((cell) => ({
        area_m2: cell.area_m2, altitude_m: cell.altitude_m, slope_deg: Math.min(80, cell.slope_deg),
      })),
      latitude: center?.[0], longitude: center?.[1], slope_deg: slope,
      region: region.value.trim(), irrigation_mm_day: irrigation.valueAsNumber,
      evaluate_uncertainty: uncertainty.checked,
      delta_T_whatif: state.climateDeltaT ?? 0,
      delta_P_pct_whatif: state.climateDeltaPct ?? 0,
      residue_fraction: residue.valueAsNumber / 100, irrigation_cost_pen_mm_ha: irrigationCost.valueAsNumber,
      costs_pen_ha: Object.fromEntries(costInputs.filter(([, , input]) => input.value !== '')
        .map(([id, , input]) => [id, input.valueAsNumber])),
    };
    const physicalSignature = message || JSON.stringify([state.selectedParcel.id, physicalInput]);
    const knobSignature = JSON.stringify(state.knobs);

    if (!force && physicalSignature === lastPhysicalSignature) {
      if (knobSignature === lastKnobSignature) return;
      lastKnobSignature = knobSignature;
      if (!message && lastData && lastDataSignature === physicalSignature && Array.isArray(lastData.candidates)) {
        renderRecommendation(lastData, state.knobs);
        return;
      }
      if (message) return;
      // Physical simulation is still in flight or lacks cached candidates; let it resolve or re-fetch if idle.
      if (controller && !controller.signal.aborted) return;
    }

    lastPhysicalSignature = physicalSignature;
    lastKnobSignature = knobSignature;
    cancel();
    retry.hidden = true;
    if (message) {
      lastData = null;
      lastDataSignature = '';
      result.replaceChildren();
      status.textContent = message;
      return;
    }
    if (!lastData || lastDataSignature !== physicalSignature) {
      result.replaceChildren();
      status.textContent = 'Calculating crop rotation…';
    }
    const current = new AbortController();
    controller = current;
    timer = setTimeout(async () => {
      try {
        const data = await fetchRotation({ ...physicalInput, weights: state.knobs }, current.signal);
        if (current.signal.aborted) return;
        lastData = data;
        lastDataSignature = physicalSignature;
        renderRecommendation(data, state.knobs);
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
