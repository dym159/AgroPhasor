import { createCenterStage } from './components/centerStage.js';
import { createCropsPanel } from './components/cropsPanel.js';
import { createKnobsPanel } from './components/knobsPanel.js';
import { renderParcelBar } from './components/parcelBar.js';
import { createRotationsPanel } from './components/rotationsPanel.js';
import { renderStrategyPanel } from './components/strategyPanel.js';
import { createTimelineBar } from './components/timelineBar.js';
import { STRATEGY_MODES } from './data/mockVisualData.js';
import { fetchCropCatalog, fetchParcelSimulation } from './services/agroApi.js';
import { createUiState } from './state/uiState.js';
import { addDays, applyTimelineSnapshot, assignPhaseCrop } from './utils/phaseDates.js';

function rebalanceKnobs(currentKnobs, changedId, nextValue) {
  const clamped = Math.max(0, Math.min(100, Math.round(nextValue)));
  const otherKeys = Object.keys(currentKnobs).filter((k) => k !== changedId);
  const remainder = 100 - clamped;
  const otherSum = otherKeys.reduce((acc, k) => acc + (currentKnobs[k] ?? 0), 0);

  const nextKnobs = { ...currentKnobs, [changedId]: clamped };
  let unassigned = remainder;
  const fractions = otherKeys.map((key) => {
    const share = otherSum > 0
      ? remainder * currentKnobs[key] / otherSum
      : remainder / otherKeys.length;
    nextKnobs[key] = Math.floor(share);
    unassigned -= nextKnobs[key];
    return { key, fraction: share - nextKnobs[key] };
  });
  fractions.sort((a, b) => b.fraction - a.fraction);
  for (const { key } of fractions.slice(0, unassigned)) nextKnobs[key]++;
  return nextKnobs;
}

function bootstrapApp() {
  const parcelBarEl = document.getElementById('parcel-bar');
  const strategyEl = document.getElementById('strategy-panel');
  const knobsEl = document.getElementById('knobs-panel');
  const centerEl = document.getElementById('center-stage');
  const cropsEl = document.getElementById('crops-panel');
  const rotationsEl = document.getElementById('rotations-panel');
  const timelineEl = document.getElementById('timeline-bar');

  const store = createUiState();
  const rotationsPanel = createRotationsPanel(rotationsEl);
  let parcelSimulationController = null;
  let parcelSimulationTimer = null;
  let lastParcelSignature = '';

  function scheduleParcelSimulation({ retry = false } = {}) {
    const state = store.getState();
    const hasParcel = state.hasActiveTerrain && state.selectedParcel?.polygon?.length;
    const isPlanActive = !state.isBareSoil && state.phases.length > 0 && state.phases.every((phase) => phase.cropId && phase.harvest);
    const defaultPlanDate = isPlanActive
      ? (addDays(state.phases.at(-1).harvest, -1) || state.phases.at(-1).harvest)
      : state.phases[0]?.start;
    const effectiveSimDate = isPlanActive
      && state.simulationDate
      && state.simulationDate >= state.phases[0].start
      && state.simulationDate <= state.phases.at(-1).harvest
      ? state.simulationDate
      : defaultPlanDate;
    const activePhase = state.phases.find((phase) => phase.start <= (effectiveSimDate ?? state.phases[0]?.start)
      && (phase.harvest ?? '9999-12-31') >= (effectiveSimDate ?? state.phases[0]?.start));
    const selectedCrop = activePhase?.cropId ?? state.phases.find((phase) => phase.cropId)?.cropId ?? state.previewCropId;
    const cropId = state.isBareSoil ? 'transicion' : selectedCrop ?? 'papa';
    if (!hasParcel) {
      parcelSimulationController?.abort();
      clearTimeout(parcelSimulationTimer);
      lastParcelSignature = '';
      store.setState({
        parcelSimulationResult: null,
        parcelSimulationFailed: false,
        parcelSimulationStatusText: 'Draw your parcel boundary on the map.',
      });
      return;
    }

    const signature = JSON.stringify([
      state.selectedParcel.id,
      state.selectedParcel.polygon,
      isPlanActive ? 'plan' : cropId,
      state.phases,
      isPlanActive && state.parcelSimulationResult?.timeline_snapshots?.length ? 'cached-timeline' : effectiveSimDate,
      state.climateDeltaT,
      state.climateDeltaPct,
      !state.isBareSoil && !selectedCrop,
    ]);
    if (!retry && signature === lastParcelSignature) return;
    lastParcelSignature = signature;

    parcelSimulationController?.abort();
    clearTimeout(parcelSimulationTimer);

    const controller = new AbortController();
    parcelSimulationController = controller;

    store.setState({
      parcelSimulationResult: null,
      parcelSimulationFailed: false,
      parcelSimulationStatusText: state.isBareSoil
        ? 'Computing bare soil with NASA POWER and SRTM…'
        : 'Computing thermal shield with NASA POWER and SRTM…',
    });

    parcelSimulationTimer = setTimeout(async () => {
      try {
        const result = await fetchParcelSimulation(
          state.selectedParcel,
          cropId,
          controller.signal,
          isPlanActive
            ? {
                phases: state.phases,
                selected_date: effectiveSimDate,
                delta_T_whatif: state.climateDeltaT ?? 0,
                delta_P_pct_whatif: state.climateDeltaPct ?? 0,
              }
            : {}
        );
        if (controller.signal.aborted) return;

        const hydrated = isPlanActive && result.timeline_snapshots?.length
          ? applyTimelineSnapshot(result, effectiveSimDate)
          : result;

        const cropLabel = hydrated.reference_crop_used || (!state.isBareSoil && !selectedCrop)
          ? `${hydrated.crop} (reference)` : hydrated.crop;
        const phaseTag = hydrated.plan_simulation
          ? ` (${hydrated.phase === 'transicion' ? 'Fallow' : `Phase ${(hydrated.phase_index ?? 0) + 1}`})`
          : '';

        store.setState({
          ...(isPlanActive && !state.simulationDate ? { simulationDate: effectiveSimDate } : {}),
          parcelSimulationResult: hydrated,
          parcelSimulationStatusText: `${cropLabel}${phaseTag} · ${hydrated.date} · ${hydrated.cells_count} 30 m cells`,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        store.setState({
          parcelSimulationFailed: true,
          parcelSimulationStatusText: error.message,
        });
      }
    }, 250);
  }

  const knobsPanel = createKnobsPanel(
    knobsEl,
    store.getState().knobs,
    (knobId, value) => {
      const current = store.getState();
      if (current.knobsLocked || current.knobs[knobId] === value) return;
      const nextKnobs = rebalanceKnobs(current.knobs, knobId, value);
      store.setState({ knobs: nextKnobs, selectedSubRouteId: null, rotationRequested: true });
    },
    () => store.setState({ knobsLocked: !store.getState().knobsLocked })
  );

  function updateSelectedCrops(ids, preferredCropId) {
    store.setState({
      selectedCropIds: ids,
      previewCropId: ids.includes(preferredCropId) ? preferredCropId : ids.at(-1) ?? null,
      ...(ids.length ? { rotationRequested: true } : {}),
    });
    scheduleParcelSimulation();
  }

  const cropsPanel = createCropsPanel(cropsEl, store.getState(), {
    onSearchCrop: (query) => store.setState({ cropSearchQuery: query }),
    onSelectGroup: (group) => store.setState({ activeCropGroup: group }),
    onToggleCrop: (cropId) => {
      const current = store.getState();
      const exists = current.selectedCropIds.includes(cropId);
      const nextIds = exists
        ? current.selectedCropIds.filter((id) => id !== cropId)
        : [...current.selectedCropIds, cropId];
      updateSelectedCrops(nextIds, exists ? current.previewCropId : cropId);
    },
    onSelectBatch: (batchIds) => {
      const current = store.getState();
      const merged = Array.from(new Set([...current.selectedCropIds, ...batchIds]));
      updateSelectedCrops(merged, current.previewCropId ?? batchIds[0]);
    },
    onClearCrops: () => updateSelectedCrops([], null),
  });

  const timelineBar = createTimelineBar(timelineEl, store.getState(), {
    onInspectDate: (simulationDate) => {
      const current = store.getState();
      if (!current.isBareSoil && current.parcelSimulationResult?.timeline_snapshots?.length) {
        const hydrated = applyTimelineSnapshot(current.parcelSimulationResult, simulationDate);
        const phaseTag = hydrated.plan_simulation
          ? ` (${hydrated.phase === 'transicion' ? 'Fallow' : `Phase ${(hydrated.phase_index ?? 0) + 1}`})`
          : '';
        store.setState({
          simulationDate,
          parcelSimulationResult: hydrated,
          parcelSimulationStatusText: `${hydrated.crop}${phaseTag} · ${hydrated.date} · ${hydrated.cells_count} 30 m cells`,
        });
        return;
      }
      store.setState({ simulationDate });
      scheduleParcelSimulation();
    },
    onPlantingStart: (plantingStart) => {
      if (store.getState().plantingStart !== plantingStart) store.setState({ plantingStart });
    },
    onAddPhase: (start) => {
      const { phases: existing, previewCropId, cropCycles } = store.getState();
      const last = existing.at(-1);
      if (last && start <= last.start) return;
      const prefix = last && last.harvest !== start
        ? [...existing.slice(0, -1), { ...last, harvest: start, manualEnd: true }]
        : existing;
      const cropId = last ? '' : previewCropId ?? '';
      const phases = assignPhaseCrop([...prefix, { start }], prefix.length, cropId, cropCycles);
      const lastAdded = phases.at(-1);
      const nextSimDate = lastAdded?.harvest
        ? (addDays(lastAdded.harvest, -1) || lastAdded.harvest)
        : store.getState().simulationDate;
      store.setState({ phases, ...(nextSimDate ? { simulationDate: nextSimDate } : {}) });
      scheduleParcelSimulation();
    },
    onAssignCrop: (phaseIndex, cropId) => {
      const { phases, cropCycles } = store.getState();
      const phase = phases[phaseIndex];
      if (!phase || phase.cropId === cropId) return;
      if (cropId && !Object.hasOwn(cropCycles, cropId)) return;

      const nextPhases = assignPhaseCrop(phases, phaseIndex, cropId, cropCycles);
      const assignedPhase = nextPhases[phaseIndex];
      const nextSimDate = assignedPhase?.harvest
        ? (addDays(assignedPhase.harvest, -1) || assignedPhase.harvest)
        : store.getState().simulationDate;
      store.setState({ phases: nextPhases, ...(nextSimDate ? { simulationDate: nextSimDate } : {}) });
      scheduleParcelSimulation();
    },
    onClimateWhatIf: (climateDeltaT, climateDeltaPct) => {
      store.setState({ climateDeltaT, climateDeltaPct });
      scheduleParcelSimulation();
    },
  });

  const handleDeleteTerrain = () => {
    lastParcelSignature = '';
    parcelSimulationController?.abort();
    clearTimeout(parcelSimulationTimer);
    store.setState({
      hasActiveTerrain: false,
      selectedParcel: null,
      centerMode: 'select',
      parcelSimulationResult: null,
      parcelSimulationFailed: false,
      parcelSimulationStatusText: 'Parcel removed. Select or draw another parcel.',
    });
  };

  const centerStage = createCenterStage(centerEl, {
    onCustomPolygonDrawn: (polygonCoords) => {
      if (!polygonCoords?.length) return;
      const centerLat =
        polygonCoords.reduce((acc, pt) => acc + pt[0], 0) / polygonCoords.length;
      const centerLng =
        polygonCoords.reduce((acc, pt) => acc + pt[1], 0) / polygonCoords.length;

      store.setState({
        selectedParcel: {
          id: `custom-${Date.now()}`,
          name: 'Selected parcel',
          center: [centerLat, centerLng],
          polygon: polygonCoords,
        },
        hasActiveTerrain: true,
        parcelSimulationResult: null,
      });
      scheduleParcelSimulation();
    },
    onConfirmTerrain: () => {
      store.setState({ centerMode: 'terrain' });
    },
    onBackToMap: () => {
      store.setState({ centerMode: 'select' });
    },
    onToggleBareSoil: () => {
      store.setState({ isBareSoil: !store.getState().isBareSoil });
      scheduleParcelSimulation();
    },
    onRetrySimulation: () => scheduleParcelSimulation({ retry: true }),
    onDeleteTerrain: handleDeleteTerrain,
  });

  function renderAll(state) {
    renderParcelBar(parcelBarEl, state, {
      onChangeMode: (mode) => store.setState({ centerMode: mode }),
      onDeleteTerrain: handleDeleteTerrain,
    });

    renderStrategyPanel(strategyEl, state, {
      onSelectStrategy: (strategyId, subRouteId) => {
        const strategy = STRATEGY_MODES.find((mode) => mode.id === strategyId);
        const branch = strategy.subRoutes.find((route) => route.id === subRouteId);
        store.setState({
          selectedStrategyId: strategyId,
          selectedSubRouteId: subRouteId,
          knobs: store.getState().knobsLocked ? store.getState().knobs : branch?.weights ?? strategy.weights,
          rotationRequested: true,
        });
      },
    });

    knobsPanel.update(state.knobs, state.knobsLocked);
    cropsPanel.update(state);
    rotationsPanel.update(state);

    timelineBar.update(state);
    centerStage.render(state);
  }

  store.subscribe(renderAll);
  renderAll(store.getState());
  scheduleParcelSimulation();
  fetchCropCatalog().then((cropCatalog) => {
    const cropCycles = Object.fromEntries(Object.entries(cropCatalog)
      .map(([id, crop]) => [id, crop.duration_days]));
    const { phases } = store.getState();
    const pending = phases.findIndex((phase) => !phase.harvest && cropCycles[phase.cropId]);
    store.setState({
      cropCatalog, cropCycles,
      ...(pending >= 0 ? { phases: assignPhaseCrop(phases, pending, phases[pending].cropId, cropCycles) } : {}),
    });
  }).catch((error) => {
    console.error(error);
  });
}

document.addEventListener('DOMContentLoaded', bootstrapApp);
