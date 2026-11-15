import { createCenterStage } from './components/centerStage.js';
import { createCropsPanel } from './components/cropsPanel.js';
import { createKnobsPanel } from './components/knobsPanel.js';
import { renderParcelBar } from './components/parcelBar.js';
import { renderRotationsPanel } from './components/rotationsPanel.js';
import { renderStrategyPanel } from './components/strategyPanel.js';
import { createTimelineBar } from './components/timelineBar.js';
import { ROTATION_TYPES, STRATEGY_MODES } from './data/mockVisualData.js';
import { fetchParcelEdo1, fetchSimulation } from './services/agroApi.js';
import { createUiState } from './state/uiState.js';

function rebalanceKnobs(currentKnobs, changedId, nextValue) {
  const clamped = Math.max(0, Math.min(100, Math.round(nextValue)));
  const otherKeys = Object.keys(currentKnobs).filter((k) => k !== changedId);
  const remainder = 100 - clamped;
  const otherSum = otherKeys.reduce((acc, k) => acc + (currentKnobs[k] ?? 0), 0);

  const nextKnobs = { ...currentKnobs, [changedId]: clamped };
  if (otherSum <= 0) {
    const share = Math.floor(remainder / otherKeys.length);
    otherKeys.forEach((k, idx) => {
      nextKnobs[k] = idx === 0 ? remainder - share * (otherKeys.length - 1) : share;
    });
    return nextKnobs;
  }

  let assigned = 0;
  otherKeys.forEach((k, idx) => {
    if (idx === otherKeys.length - 1) {
      nextKnobs[k] = Math.max(0, remainder - assigned);
    } else {
      const scaled = Math.round(((currentKnobs[k] ?? 0) / otherSum) * remainder);
      nextKnobs[k] = scaled;
      assigned += scaled;
    }
  });
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
  let edo1Controller = null;
  let edo1Timer = null;
  let lastEdo1Signature = '';

  function scheduleEdo1Simulation() {
    const state = store.getState();
    if (!state.hasActiveTerrain || !state.selectedParcel?.polygon?.length) {
      edo1Controller?.abort();
      store.setState({
        edo1Result: null,
        edo1StatusText: 'Selecciona o dibuja un terreno en el mapa.',
      });
      return;
    }

    const signature = JSON.stringify([
      state.selectedParcel.id,
      state.selectedParcel.polygon,
      state.previewCropId,
    ]);
    if (signature === lastEdo1Signature) return;
    lastEdo1Signature = signature;

    edo1Controller?.abort();
    clearTimeout(edo1Timer);

    const controller = new AbortController();
    edo1Controller = controller;

    store.setState({
      edo1StatusText: 'Consultando NASA POWER (T2M) + SRTM v3 (30m)...',
    });

    edo1Timer = setTimeout(async () => {
      try {
        const result = await fetchParcelEdo1(
          state.selectedParcel,
          state.previewCropId,
          controller.signal
        );
        if (controller.signal.aborted) return;

        const waterStr = result.lot_mean_soil_water_mm != null
          ? ` · EDO 2: Agua ${result.lot_mean_soil_water_mm} mm (${result.water_status})`
          : '';
        const biomassStr = result.lot_mean_biomass_t_ha != null
          ? ` · EDO 4: Biomasa ${result.lot_mean_biomass_t_ha} t/ha (NDVI ${result.lot_mean_ndvi})`
          : '';
        const irrStr = result.irrigation_alert && result.suggested_irrigation_mm > 0
          ? ` · 💧 Riego ${result.suggested_irrigation_mm} mm`
          : '';
        const erosionStr = result.lot_mean_erosion_loss_mm != null
          ? ` · EDO 5: Erosión ${result.lot_mean_erosion_loss_mm} mm (${result.erosion_risk_level})`
          : '';

        store.setState({
          edo1Result: result,
          edo1StatusText: `EDOs 1-5 · ${result.cells_count} celdas 30m · Dosel ${result.lot_mean_temp} °C${waterStr}${biomassStr}${irrStr}${erosionStr} · (NASA GPM/POWER/SMAP + SRTM)`,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        store.setState({
          edo1StatusText: `EDO 1: ${error.message}`,
        });
      }
    }, 250);
  }

  async function syncCc09Simulation() {
    const state = store.getState();
    if (!state.hasActiveTerrain) return;
    const sim = await fetchSimulation(
      state.selectedParcel,
      state.selectedStrategyId,
      state.knobs
    );
    if (!sim) return;

    const backendRoute = sim.rotacion_recomendada?.ruta_seleccionada;
    const matchedRotation = ROTATION_TYPES.find((r) => r.backendRoute === backendRoute);
    store.setState({
      simulationResult: sim,
      ...(matchedRotation ? { selectedRotationId: matchedRotation.id } : {}),
    });
  }

  const knobsPanel = createKnobsPanel(
    knobsEl,
    store.getState().knobs,
    (knobId, value) => {
      const current = store.getState();
      const nextKnobs = rebalanceKnobs(current.knobs, knobId, value);
      store.setState({ knobs: nextKnobs });
      syncCc09Simulation();
    }
  );

  const cropsPanel = createCropsPanel(cropsEl, store.getState(), {
    onSearchCrop: (query) => store.setState({ cropSearchQuery: query }),
    onSelectGroup: (group) => store.setState({ activeCropGroup: group }),
    onToggleCrop: (cropId) => {
      const current = store.getState();
      const exists = current.selectedCropIds.includes(cropId);
      const nextIds = exists
        ? current.selectedCropIds.filter((id) => id !== cropId)
        : [...current.selectedCropIds, cropId];
      store.setState({
        selectedCropIds: nextIds,
        previewCropId: cropId,
      });
      scheduleEdo1Simulation();
    },
    onSelectBatch: (batchIds) => {
      const current = store.getState();
      const merged = Array.from(new Set([...current.selectedCropIds, ...batchIds]));
      store.setState({
        selectedCropIds: merged,
        previewCropId: batchIds[0] ?? current.previewCropId,
      });
      scheduleEdo1Simulation();
    },
    onClearCrops: () => {
      store.setState({ selectedCropIds: [] });
    },
  });

  const timelineBar = createTimelineBar(timelineEl, store.getState(), {
    onChangeMonth: (monthIndex) => store.setState({ activeMonthIndex: monthIndex }),
    onAddPeriod: () => {
      const current = store.getState();
      store.setState({ periodCount: Math.min(6, current.periodCount + 1) });
    },
  });

  const handleDeleteTerrain = () => {
    lastEdo1Signature = '';
    edo1Controller?.abort();
    store.setState({
      hasActiveTerrain: false,
      centerMode: 'select',
      edo1Result: null,
      edo1StatusText: 'Terreno eliminado. Selecciona o dibuja otro lote.',
    });
  };

  const centerStage = createCenterStage(centerEl, {
    onSelectPresetParcel: (parcel) => {
      store.setState({
        selectedParcel: parcel,
        hasActiveTerrain: true,
        edo1Result: null,
      });
      scheduleEdo1Simulation();
      syncCc09Simulation();
    },
    onCustomPolygonDrawn: (polygonCoords) => {
      if (!polygonCoords?.length) return;
      const centerLat =
        polygonCoords.reduce((acc, pt) => acc + pt[0], 0) / polygonCoords.length;
      const centerLng =
        polygonCoords.reduce((acc, pt) => acc + pt[1], 0) / polygonCoords.length;

      store.setState({
        selectedParcel: {
          id: `custom-${Date.now()}`,
          name: 'Terreno Satelital Dibujado',
          center: [centerLat, centerLng],
          polygon: polygonCoords,
        },
        hasActiveTerrain: true,
        edo1Result: null,
      });
      scheduleEdo1Simulation();
      syncCc09Simulation();
    },
    onConfirmTerrain: () => {
      store.setState({ centerMode: 'terrain' });
    },
    onBackToMap: () => {
      store.setState({ centerMode: 'select' });
    },
    onDeleteTerrain: handleDeleteTerrain,
  });

  function renderAll(state) {
    renderParcelBar(parcelBarEl, state, {
      onChangeMode: (mode) => store.setState({ centerMode: mode }),
      onDeleteTerrain: handleDeleteTerrain,
    });

    renderStrategyPanel(strategyEl, state, {
      onSelectStrategy: (strategyId, subRouteId) => {
        const modeSpec = STRATEGY_MODES.find((m) => m.id === strategyId);
        const subSpec = modeSpec?.subRoutes.find((s) => s.id === subRouteId);
        store.setState({
          selectedStrategyId: strategyId,
          selectedSubRouteId: subRouteId,
          ...(subSpec?.knobs
            ? { knobs: { ...subSpec.knobs } }
            : modeSpec?.defaultKnobs
              ? { knobs: { ...modeSpec.defaultKnobs } }
              : {}),
          ...(subSpec?.rotationId ? { selectedRotationId: subSpec.rotationId } : {}),
        });
        syncCc09Simulation();
      },
    });

    knobsPanel.update(state.knobs);
    cropsPanel.update(state);

    renderRotationsPanel(rotationsEl, state, (rotationId) => {
      store.setState({ selectedRotationId: rotationId });
    });

    timelineBar.update(state);
    centerStage.render(state);
  }

  store.subscribe(renderAll);
  renderAll(store.getState());
  scheduleEdo1Simulation();
  syncCc09Simulation();
}

document.addEventListener('DOMContentLoaded', bootstrapApp);
