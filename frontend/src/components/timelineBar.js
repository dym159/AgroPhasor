import { CROP_DRAG_TYPE, TIMELINE_MONTHS, VISUAL_CROPS } from '../data/mockVisualData.js';
import { clearChildren, createElement } from '../utils/dom.js';
import { formatPhaseDate, monthStart } from '../utils/phaseDates.js';

export function createTimelineBar(container, initialState, callbacks) {
  if (!container) return { update: () => {} };

  clearChildren(container);
  let state = initialState;
  let monthIndex = 0;

  const yearInput = createElement('input', {
    type: 'number',
    attrs: { min: 1900, max: 9999, step: 1, required: '' },
  });
  const yearLabel = createElement('label', { className: 'timeline-year' }, ['Año', yearInput]);
  const tickButtons = TIMELINE_MONTHS.map((month, index) => createElement('button', {
    type: 'button', className: 'month-tick', text: month,
    onClick: () => selectMonth(index),
  }));
  const slider = createElement('input', {
    type: 'range', className: 'timeline-slider',
    attrs: { min: 0, max: TIMELINE_MONTHS.length - 1 },
  });
  const phaseLabel = createElement('span', {
    className: 'timeline-phase-label', attrs: { 'aria-live': 'polite' },
  });
  const addPhaseBtn = createElement('button', {
    type: 'button', className: 'btn btn-compact', text: '+ Fase',
    onClick: () => {
      if (!addPhaseBtn.disabled) callbacks.onAddPhase(selectedDate());
    },
  });
  const phaseList = createElement('div', {
    className: 'timeline-phases',
    attrs: { role: 'group', 'aria-label': 'Línea de tiempo de siembra' },
  });

  container.append(
    createElement('div', { className: 'timeline-ticks' }, tickButtons),
    slider,
    createElement('div', { className: 'timeline-bottom' }, [yearLabel, phaseLabel, addPhaseBtn]),
    phaseList,
  );

  const inspectionDate = createElement('input', { type: 'date', attrs: { 'aria-label': 'Fecha a simular' } });
  const inspectButton = createElement('button', {
    type: 'button', className: 'btn btn-compact', text: 'Simular fecha',
    onClick: () => {
      if (inspectionDate.value && inspectionDate.checkValidity()) callbacks.onInspectDate(inspectionDate.value);
    },
  });
  const inspection = createElement('label', { className: 'timeline-bottom' }, [
    'Evolución del terreno', inspectionDate, inspectButton,
  ]);
  container.append(inspection);

  yearInput.addEventListener('input', changeDate);
  slider.addEventListener('input', () => selectMonth(slider.valueAsNumber));

  function selectMonth(index) {
    monthIndex = index;
    changeDate();
  }

  function selectedDate() {
    if (!yearInput.validity.valid) return null;
    const month = monthStart(yearInput.valueAsNumber, monthIndex);
    const harvest = state.phases.at(-1)?.harvest;
    return harvest?.slice(0, 7) === month.slice(0, 7) ? harvest : month;
  }

  function changeDate() {
    const date = selectedDate();
    if (!state.phases.length && date) callbacks.onPlantingStart(date);
    updateSelection();
  }

  function updateSelection() {
    const last = state.phases.at(-1);
    const date = selectedDate();
    addPhaseBtn.disabled = !date || Boolean(last && date <= last.start);
    slider.value = String(monthIndex);
    slider.setAttribute('aria-label', last ? 'Mes de fin de la última fase' : 'Mes de inicio de la primera fase');
    slider.setAttribute('aria-valuetext', `${TIMELINE_MONTHS[monthIndex]} ${yearInput.value}`);
    tickButtons.forEach((btn, index) => {
      btn.classList.toggle('is-active', index === monthIndex);
      btn.setAttribute('aria-pressed', String(index === monthIndex));
    });
    phaseLabel.textContent = addPhaseBtn.disabled
      ? last ? 'Elige un fin posterior al inicio.' : 'Ingresa un año válido.'
      : `${last ? 'Fin de fase / siguiente inicio' : 'Inicio de la primera fase'} · ${formatPhaseDate(date)}`;
  }

  function syncDate() {
    const last = state.phases.at(-1);
    const date = last?.harvest ?? last?.start ?? state.plantingStart;
    const [year, month] = date.split('-').map(Number);
    yearInput.value = String(year);
    monthIndex = month - 1;
  }

  function renderPhases() {
    phaseList.hidden = state.phases.length === 0;
    inspection.hidden = !state.phases.length || state.phases.some((phase) => !phase.cropId || !phase.harvest);
    if (!inspection.hidden) {
      inspectionDate.min = state.phases[0].start;
      inspectionDate.max = state.phases.at(-1).harvest;
      inspectionDate.value = state.simulationDate ?? state.phases[0].start;
    }
    phaseList.replaceChildren(...state.phases.map((phase, index) => {
      const start = formatPhaseDate(phase.start);
      const cropSelect = createElement('select', {
        className: 'timeline-phase-crop', attrs: { 'aria-label': `Cultivo desde ${start}` },
      }, [
        createElement('option', { text: 'Sin cultivo', attrs: { value: '' } }),
        ...VISUAL_CROPS.map((crop) => createElement('option', {
          text: crop.name, attrs: { value: crop.id },
        })),
      ]);
      cropSelect.value = phase.cropId;
      cropSelect.addEventListener('change', () => callbacks.onAssignCrop(index, cropSelect.value));
      const segment = createElement('div', {
        className: 'timeline-phase', attrs: { role: 'group', 'aria-label': `Fase ${index + 1}` },
      }, [
        createElement('span', { className: 'timeline-phase-date', text: `Inicio · ${start}` }),
        createElement('span', { className: 'timeline-phase-date', text: phase.harvest
          ? `${phase.manualEnd ? 'Fin manual' : 'Cosecha estimada'} · ${formatPhaseDate(phase.harvest)}`
          : phase.cropId ? 'Define el mes y año de fin' : 'Elige un cultivo' }),
        cropSelect,
      ]);
      segment.addEventListener('dragover', (event) => {
        if (!event.dataTransfer.types.includes(CROP_DRAG_TYPE)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
        segment.classList.add('is-drop-target');
      });
      segment.addEventListener('dragleave', (event) => {
        if (!segment.contains(event.relatedTarget)) segment.classList.remove('is-drop-target');
      });
      segment.addEventListener('drop', (event) => {
        event.preventDefault();
        segment.classList.remove('is-drop-target');
        const cropId = event.dataTransfer.getData(CROP_DRAG_TYPE);
        if (cropId) callbacks.onAssignCrop(index, cropId);
      });
      return segment;
    }));
    updateSelection();
  }

  function update(next) {
    const phasesChanged = next.phases !== state.phases;
    const added = next.phases.length > state.phases.length;
    state = next;
    if (!phasesChanged) return;
    syncDate();
    renderPhases();
    if (added) phaseList.scrollLeft = phaseList.scrollWidth;
  }

  syncDate();
  renderPhases();
  return { update };
}
