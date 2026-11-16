import {
  CROP_GROUPS,
  PDF_KNOBS,
  STRATEGY_MODES,
} from '../data/mockVisualData.js';
import { monthStart } from '../utils/phaseDates.js';

export function createUiState() {
  const initialKnobs = Object.fromEntries(
    PDF_KNOBS.map((knob) => [knob.id, knob.defaultValue])
  );

  const today = new Date();
  let state = {
    centerMode: 'select',
    selectedParcel: null,
    hasActiveTerrain: false,
    selectedStrategyId: STRATEGY_MODES[1].id,
    selectedSubRouteId: null,
    knobs: initialKnobs,
    knobsLocked: false,
    rotationRequested: false,
    activeCropGroup: CROP_GROUPS[0],
    cropSearchQuery: '',
    selectedCropIds: [],
    previewCropId: null,
    isBareSoil: false,
    phases: [],
    plantingStart: monthStart(today.getFullYear(), today.getMonth()),
    climateDeltaT: 0,
    climateDeltaPct: 0,
    cropCycles: {},
    cropCatalog: {},
    parcelSimulationResult: null,
    parcelSimulationFailed: false,
    parcelSimulationStatusText: '',
  };

  const listeners = new Set();

  function getState() {
    return state;
  }

  function setState(patch) {
    state = { ...state, ...patch };
    for (const listener of listeners) {
      listener(state);
    }
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return { getState, setState, subscribe };
}
