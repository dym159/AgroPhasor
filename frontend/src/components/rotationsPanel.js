import { ROTATION_TYPES, STRATEGY_MODES } from '../data/mockVisualData.js';
import { clearChildren, createElement } from '../utils/dom.js';

export function renderRotationsPanel(container, state, onSelectRotation) {
  if (!container) return;

  clearChildren(container);

  const header = createElement('div', { className: 'panel-header' }, [
    createElement('h2', { className: 'panel-title', text: 'Tipos de Rotación' }),
  ]);

  const list = createElement('div', { className: 'rotations-list panel-scroll' });
  const recommendation = renderRecommendation(state);
  list.append(recommendation);

  for (const rotation of ROTATION_TYPES) {
    const isSelected = state.selectedRotationId === rotation.id;

    const card = createElement(
      'button',
      {
        type: 'button',
        className: `rotation-card ${isSelected ? 'is-selected' : ''}`,
        onClick: () => onSelectRotation(rotation.id),
      },
      [
        createElement('span', { className: 'rotation-indicator' }),
        createElement('span', { className: 'rotation-name', text: rotation.name }),
      ]
    );

    list.append(card);
  }

  container.append(header, list);
}

function renderRecommendation(state) {
  const suggestion = state.simulationResult?.rotacion_recomendada?.sugerencia_optimizada;
  const strategy = STRATEGY_MODES.find((mode) => mode.id === state.selectedStrategyId);
  const branch = strategy?.subRoutes.find((route) => route.id === state.selectedSubRouteId);
  const source = state.recommendationSource === 'knobs'
    ? 'Según tus perillas'
    : `Según ${[strategy?.label, branch?.label].filter(Boolean).join(' · ')}`;
  const heading = createElement('h3', { text: 'Rotación recomendada' });
  const details = [];

  if (state.hasActiveTerrain && state.recommendationStatus === 'ready' && suggestion?.length) {
    details.push(
      createElement('p', { text: source }),
      createElement('ol', {}, suggestion.map(({ cultivo, periodo }) =>
        createElement('li', {}, [
          createElement('strong', { text: cultivo }),
          createElement('span', { text: periodo }),
        ])
      ))
    );
  } else {
    let message = 'Calculando la rotación…';
    if (!state.hasActiveTerrain) message = 'Selecciona un terreno para ver la recomendación.';
    else if (state.recommendationStatus === 'error') message = 'No se pudo cargar la recomendación.';
    details.push(createElement('p', { text: message }));
  }

  return createElement('section', { className: 'rotation-recommendation', attrs: { role: 'status' } }, [
    heading, ...details,
  ]);
}
