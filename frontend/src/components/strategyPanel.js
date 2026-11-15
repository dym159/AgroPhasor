import { STRATEGY_MODES } from '../data/mockVisualData.js';
import { clearChildren, createElement } from '../utils/dom.js';

export function renderStrategyPanel(container, state, callbacks) {
  if (!container) return;

  clearChildren(container);

  const shieldScore = state.simulationResult?.indicadores?.escudo_ambiental?.indice;
  const headerChildren = [
    createElement('h2', { className: 'panel-title', text: 'Estrategias' }),
  ];
  if (shieldScore != null) {
    headerChildren.push(
      createElement('span', { className: 'panel-tag', text: `Escudo ${shieldScore}/100` })
    );
  }

  const header = createElement('div', { className: 'panel-header' }, headerChildren);
  const list = createElement('div', { className: 'strategy-list panel-scroll' });

  for (const mode of STRATEGY_MODES) {
    const isSelected = state.selectedStrategyId === mode.id;

    const dot = createElement('span', {
      className: 'strategy-dot',
      style: { color: mode.accentColor },
    });

    const mainButton = createElement(
      'button',
      {
        type: 'button',
        className: `strategy-card ${isSelected ? 'is-selected' : ''}`,
        onClick: () => callbacks.onSelectStrategy(mode.id, mode.subRoutes[0].id),
      },
      [dot, createElement('span', { className: 'strategy-name', text: mode.label })]
    );

    const branchList = createElement('div', { className: 'branch-list' });
    for (const subRoute of mode.subRoutes) {
      const isBranchActive = isSelected && state.selectedSubRouteId === subRoute.id;
      const chip = createElement('button', {
        type: 'button',
        className: `branch-chip ${isBranchActive ? 'is-selected' : ''}`,
        text: subRoute.label,
        onClick: () => callbacks.onSelectStrategy(mode.id, subRoute.id),
      });
      branchList.append(chip);
    }

    const group = createElement('div', { className: 'strategy-group' }, [
      mainButton,
      branchList,
    ]);
    list.append(group);
  }

  container.append(header, list);
}
