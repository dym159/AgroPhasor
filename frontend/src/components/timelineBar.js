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
  const yearLabel = createElement('label', { className: 'timeline-year' }, ['Year', yearInput]);
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
    type: 'button', className: 'btn btn-compact', text: '+ Phase',
    onClick: () => {
      if (!addPhaseBtn.disabled) callbacks.onAddPhase(selectedDate());
    },
  });
  const phaseList = createElement('div', {
    className: 'timeline-phases',
    attrs: { role: 'group', 'aria-label': 'Planting timeline' },
  });

  container.append(
    createElement('div', { className: 'timeline-ticks' }, tickButtons),
    slider,
    createElement('div', { className: 'timeline-bottom' }, [yearLabel, phaseLabel, addPhaseBtn]),
    phaseList,
  );

  const inspectionDate = createElement('input', { type: 'date', attrs: { 'aria-label': 'Date to simulate' } });
  const inspectButton = createElement('button', {
    type: 'button', className: 'btn btn-compact', text: 'Simulate date',
    onClick: () => {
      if (inspectionDate.value && inspectionDate.checkValidity()) callbacks.onInspectDate(inspectionDate.value);
    },
  });
  const inspection = createElement('label', { className: 'timeline-bottom' }, [
    'Parcel evolution', inspectionDate, inspectButton,
  ]);

  const deltaTInput = createElement('input', {
    type: 'number',
    attrs: { value: String(initialState.climateDeltaT ?? 0), min: -10, max: 15, step: '0.5', 'aria-label': 'Temperature shift (°C)' },
  });
  const deltaPInput = createElement('input', {
    type: 'number',
    attrs: { value: String(initialState.climateDeltaPct ?? 0), min: -90, max: 200, step: '5', 'aria-label': 'Precipitation change (%)' },
  });
  const applyWhatIfBtn = createElement('button', {
    type: 'button', className: 'btn btn-compact', text: 'Apply climate',
    onClick: () => {
      if (!deltaTInput.checkValidity() || !deltaPInput.checkValidity()) return;
      callbacks.onClimateWhatIf?.(deltaTInput.valueAsNumber || 0, deltaPInput.valueAsNumber || 0);
    },
  });
  const forecastSummary = createElement('summary', { text: 'Monte Carlo climate forecast' });
  const forecastMeta = createElement('p', { className: 'timeline-forecast-meta' });
  const forecastTableWrap = createElement('div', { className: 'timeline-forecast-scroll' });
  const forecastPanel = createElement('details', { className: 'timeline-forecast' }, [
    forecastSummary,
    createElement('div', { className: 'timeline-whatif' }, [
      createElement('label', {}, ['ΔT (°C)', deltaTInput]),
      createElement('label', {}, ['ΔRain (%)', deltaPInput]),
      applyWhatIfBtn,
    ]),
    forecastMeta,
    forecastTableWrap,
  ]);
  forecastPanel.hidden = true;

  container.append(inspection, forecastPanel);

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
    slider.setAttribute('aria-label', last ? 'End month of the last phase' : 'Start month of the first phase');
    slider.setAttribute('aria-valuetext', `${TIMELINE_MONTHS[monthIndex]} ${yearInput.value}`);
    tickButtons.forEach((btn, index) => {
      btn.classList.toggle('is-active', index === monthIndex);
      btn.setAttribute('aria-pressed', String(index === monthIndex));
    });
    phaseLabel.textContent = addPhaseBtn.disabled
      ? last ? 'Choose an end date after the start date.' : 'Enter a valid year.'
      : `${last ? 'Phase end / next start' : 'First phase start'} · ${formatPhaseDate(date)}`;
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
        className: 'timeline-phase-crop', attrs: { 'aria-label': `Crop starting ${start}` },
      }, [
        createElement('option', { text: 'No crop', attrs: { value: '' } }),
        ...VISUAL_CROPS.map((crop) => createElement('option', {
          text: crop.name, attrs: { value: crop.id },
        })),
      ]);
      cropSelect.value = phase.cropId;
      cropSelect.addEventListener('change', () => callbacks.onAssignCrop(index, cropSelect.value));
      const phaseForecast = state.parcelSimulationResult?.phase_forecasts?.[index];
      const forecastText = phaseForecast
        ? `Conf ${phaseForecast.confidence_pct}% · ${phaseForecast.yield_t_ha?.p50 ?? 0} t/ha · ${phaseForecast.climate?.temp_mean_c ?? '-'}°C · ${phaseForecast.climate?.precip_total_p50_mm ?? '-'} mm`
        : '';
      const forecastTitle = phaseForecast
        ? `Yield p10–p90: ${phaseForecast.yield_t_ha?.p10}–${phaseForecast.yield_t_ha?.p90} t/ha · Frost risk: ${phaseForecast.frost_risk_pct}% · Heat risk: ${phaseForecast.heat_risk_pct}% · Mean water stress: ${phaseForecast.water_stress_days_mean} d`
        : '';
      const segment = createElement('div', {
        className: 'timeline-phase', attrs: { role: 'group', 'aria-label': `Phase ${index + 1}` },
      }, [
        createElement('span', { className: 'timeline-phase-date', text: `Start · ${start}` }),
        createElement('span', { className: 'timeline-phase-date', text: phase.harvest
          ? `${phase.manualEnd ? 'Manual end' : 'Estimated harvest'} · ${formatPhaseDate(phase.harvest)}`
          : phase.cropId ? 'Set the end month and year' : 'Choose a crop' }),
        cropSelect,
        ...(forecastText ? [createElement('span', {
          className: 'timeline-phase-forecast',
          text: forecastText,
          attrs: { title: forecastTitle },
        })] : []),
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
    renderForecast();
    updateSelection();
  }

  function renderForecast() {
    const sim = state.parcelSimulationResult;
    const monthly = sim?.monthly_forecast;
    const cf = sim?.climate_forecast;
    const hasForecast = Boolean(sim?.plan_simulation && Array.isArray(monthly) && monthly.length);
    forecastPanel.hidden = !hasForecast;
    if (!hasForecast) return;

    deltaTInput.value = String(state.climateDeltaT ?? 0);
    deltaPInput.value = String(state.climateDeltaPct ?? 0);
    const confText = sim.montecarlo_confidence_pct != null ? `${sim.montecarlo_confidence_pct}% viable` : '';
    const scenarios = cf?.mc_scenarios ? `${cf.mc_scenarios} MC scenarios` : 'Monte Carlo';
    forecastSummary.textContent = `Climate forecast · ${confText} (${scenarios} · ${monthly.length} mo)`;
    const fit = cf?.fitting_window;
    forecastMeta.textContent = fit
      ? `Fitted on ${fit.start}..${fit.end} (${fit.days} d) · ${cf.components || 'Fourier + AR(1) + Bernoulli-Gamma'}`
      : sim.climate_source || '';

    const rows = monthly.map((m) => createElement('tr', {}, [
      createElement('td', { text: m.month }),
      createElement('td', { text: (m.active_crops || []).join(', ') }),
      createElement('td', { text: `${m.temp_p50_c}° (${m.temp_p10_c}–${m.temp_p90_c})` }),
      createElement('td', { text: `${m.precip_p50_mm} (${m.precip_p10_mm}–${m.precip_p90_mm})` }),
      createElement('td', { text: `${m.soil_water_p50_mm ?? '-'}` }),
      createElement('td', { text: `${m.viability_pct ?? '-'}%` }),
    ]));
    forecastTableWrap.replaceChildren(createElement('table', { className: 'timeline-forecast-table' }, [
      createElement('thead', {}, [createElement('tr', {}, [
        createElement('th', { text: 'Month' }),
        createElement('th', { text: 'Phase / Crop' }),
        createElement('th', { text: 'T (°C)' }),
        createElement('th', { text: 'Rain (mm)' }),
        createElement('th', { text: 'W (mm)' }),
        createElement('th', { text: 'Conf.' }),
      ])]),
      createElement('tbody', {}, rows),
    ]));
  }

  function update(next) {
    const phasesChanged = next.phases !== state.phases;
    const forecastChanged = next.parcelSimulationResult !== state.parcelSimulationResult
      || next.climateDeltaT !== state.climateDeltaT
      || next.climateDeltaPct !== state.climateDeltaPct;
    const added = next.phases.length > state.phases.length;
    state = next;
    if (!phasesChanged && !forecastChanged) return;
    if (phasesChanged) syncDate();
    renderPhases();
    if (added) phaseList.scrollLeft = phaseList.scrollWidth;
  }

  syncDate();
  renderPhases();
  return { update };
}
