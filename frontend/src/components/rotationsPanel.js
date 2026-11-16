import { fetchRotation, parcelToGeoJsonGeometry } from '../services/agroApi.js';
import { createRotationState, selectRotation } from '../state/rotationState.js';
import { createElement as el } from '../utils/dom.js';

const knobIds = ['w1', 'w2', 'w3', 'w4'];

export function createRotationsPanel(container) {
  if (!container) return { update() {} };

  const status = el('p', { attrs: { role: 'status', 'aria-live': 'polite' } });
  const count = el('select', { attrs: { 'aria-label': 'Cultivos por rotación' } },
    [3, 4, 5, 6].map(value => el('option', { text: String(value), attrs: { value: String(value) } })));
  count.value = '3';
  count.addEventListener('change', () => update(state));
  const department = el('select', { attrs: { 'aria-label': 'Departamento del terreno' } });
  const departmentField = el('label', {}, [el('span', { text: 'Departamento del terreno' }), department]);
  departmentField.hidden = true;
  department.addEventListener('change', () => update(state));
  const retry = el('button', {
    type: 'button', className: 'btn', text: 'Reintentar',
    onClick: () => request && model.load(request),
  });
  container.classList.add('rotation-workflow');
  container.hidden = true;
  container.replaceChildren(el('h2', { text: 'Rotación sugerida' }),
    el('label', {}, [el('span', { text: 'Cultivos por rotación' }), count]), departmentField, status, retry);

  let state, request, requestKey, knobsKey, parcelKey;
  const model = createRotationState(fetchRotation, render);

  function render(snapshot) {
    retry.hidden = snapshot.status !== 'error';
    if (snapshot.data?.status === 'region_required') {
      const placeholder = el('option', { text: 'Elige el departamento', attrs: { value: '' } });
      department.replaceChildren(placeholder, ...snapshot.data.available_regions.map(name =>
        el('option', { text: name, attrs: { value: name } })));
      department.value = '';
      departmentField.hidden = false;
      status.textContent = 'Identifica el departamento para validar las fechas de siembra.';
      return;
    }
    if (snapshot.status === 'ready') {
      const front = snapshot.data.pareto;
      const active = knobIds.map((_, i) => front.every(option => Number.isFinite(option.f_hat[i])));
      const weights = knobIds.map((id, i) => active[i] ? (state.knobs?.[id] ?? 25) : 0);
      const selected = selectRotation(front, weights.some(Boolean) ? weights : active.map(Number));
      const names = selected.stages.map(stage => state.cropCatalog?.[stage.crop_id]?.name ?? stage.crop_id);
      status.replaceChildren(
        el('strong', { text: names.join(' → ') }),
        el('small', { text: snapshot.data.region
          ? `${snapshot.data.region} · Estimación con datos de referencia.`
          : 'Estimación sin calendario regional identificado.' }),
      );
      return;
    }
    status.textContent = {
      idle: state?.selectedParcel ? 'Cargando el catálogo de cultivos…' : 'Selecciona un terreno.',
      loading: 'Calculando rotación…',
      empty: snapshot.data?.reasons?.find(item => /ventana regional|calendario documentado/.test(item.reason))?.reason
        ?? 'Sin combinación viable. Prueba con otra fecha o selección de cultivos.',
      error: snapshot.error,
    }[snapshot.status];
  }

  function update(next) {
    state = next;
    const geometry = parcelToGeoJsonGeometry(state.selectedParcel);
    const nextParcelKey = JSON.stringify([state.selectedParcel?.id, geometry]);
    if (nextParcelKey !== parcelKey) {
      parcelKey = nextParcelKey;
      department.value = '';
      departmentField.hidden = true;
    }
    container.hidden = !state.rotationRequested || !geometry;
    const available = Object.keys(state.cropCycles);
    const chosen = (state.selectedCropIds ?? []).filter(id => available.includes(id)).sort();
    const start = state.phases[0]?.start ?? state.plantingStart;
    request = !container.hidden && available.length && start ? {
      profile: 'reference',
      geometry,
      start_date: start,
      m: Number(count.value),
      mode: 'adaptive',
      ...(department.value ? { region: department.value } : {}),
      crop_ids: chosen.length > 1 ? chosen : available,
      ...(chosen.length === 1 ? { fixed: { 0: chosen[0] } } : {}),
    } : null;

    const key = JSON.stringify(request);
    const priority = JSON.stringify(state.knobs);
    if (key !== requestKey) {
      requestKey = key;
      if (request) model.load(request);
      else model.invalidate();
    } else if (priority !== knobsKey) {
      render(model.snapshot());
    }
    knobsKey = priority;
  }
  return { update };
}
