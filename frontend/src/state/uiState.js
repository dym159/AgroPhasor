import {
  CROP_GROUPS,
  DEMO_PARCELS,
  PDF_KNOBS,
  ROTATION_TYPES,
  STRATEGY_MODES,
  VISUAL_CROPS,
} from '../data/mockVisualData.js';

export function createUiState() {
  const initialKnobs = Object.fromEntries(
    PDF_KNOBS.map((knob) => [knob.id, knob.defaultValue])
  );

  let state = {
    centerMode: 'select',
    selectedParcel: DEMO_PARCELS[0],
    hasActiveTerrain: true,
    selectedStrategyId: STRATEGY_MODES[1].id,
    selectedSubRouteId: STRATEGY_MODES[1].subRoutes[0].id,
    knobs: initialKnobs,
    activeCropGroup: CROP_GROUPS[0],
    cropSearchQuery: '',
    selectedCropIds: [VISUAL_CROPS[0].id, VISUAL_CROPS[1].id, VISUAL_CROPS[3].id],
    previewCropId: VISUAL_CROPS[0].id,
    selectedRotationId: ROTATION_TYPES[0].id,
    activeMonthIndex: 2,
    periodCount: 2,
    edo1Result: null,
    edo1StatusText: '',
    simulationResult: null,
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
