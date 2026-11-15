import { ROTATION_TYPES } from '../data/mockVisualData.js';
import { clearChildren, createElement } from '../utils/dom.js';

export function renderRotationsPanel(container, state, onSelectRotation) {
  if (!container) return;

  clearChildren(container);

  const header = createElement('div', { className: 'panel-header' }, [
    createElement('h2', { className: 'panel-title', text: 'Tipos de Rotación' }),
  ]);

  const list = createElement('div', { className: 'rotations-list panel-scroll' });

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
