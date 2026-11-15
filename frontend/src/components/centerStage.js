import { mountParcelSelectorMap } from './parcelSelectorMap.js';
import { mountTerrainVisualizer } from './terrainVisualizer.js';

export function createCenterStage(container, callbacks) {
  if (!container) return { render: () => {} };

  let activeHandle = null;
  let lastMountKey = '';

  function render(state) {
    const mountKey = `${state.centerMode}:${state.selectedParcel?.id}:${state.hasActiveTerrain}`;

    if (mountKey === lastMountKey) {
      activeHandle?.update?.(state);
      return;
    }

    lastMountKey = mountKey;
    activeHandle?.destroy?.();
    activeHandle = null;

    if (state.centerMode === 'terrain' && state.hasActiveTerrain) {
      activeHandle = mountTerrainVisualizer(container, state, {
        onBackToMap: callbacks.onBackToMap,
        onDeleteTerrain: callbacks.onDeleteTerrain,
        onToggleBareSoil: callbacks.onToggleBareSoil,
        onRetrySimulation: callbacks.onRetrySimulation,
      });
      return;
    }

    activeHandle = mountParcelSelectorMap(container, state, {
      onCustomPolygonDrawn: callbacks.onCustomPolygonDrawn,
      onConfirmTerrain: callbacks.onConfirmTerrain,
      onDeleteTerrain: callbacks.onDeleteTerrain,
      onRetrySimulation: callbacks.onRetrySimulation,
    });
  }

  return { render };
}
