import { PDF_KNOBS } from '../data/mockVisualData.js';
import { clearChildren, createElement } from '../utils/dom.js';

export function createKnobsPanel(container, initialKnobs, onKnobChange, onToggleLock) {
  if (!container) return { update: () => {} };

  clearChildren(container);

  const lockButton = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Bloquear',
    attrs: { 'aria-label': 'Bloquear perillas', 'aria-pressed': false },
    onClick: onToggleLock,
  });
  const header = createElement('div', { className: 'panel-header' }, [
    createElement('h2', { className: 'panel-title', text: 'Perillas' }),
    lockButton,
  ]);

  const list = createElement('div', { className: 'knobs-list panel-scroll' });
  const controlsById = new Map();

  for (const knob of PDF_KNOBS) {
    const initialValue = initialKnobs[knob.id] ?? knob.defaultValue;
    const valueEl = createElement('span', {
      className: 'knob-value',
      text: `${initialValue}%`,
    });

    const labelEl = createElement('span', { className: 'knob-label' }, [
      createElement('span', { className: 'knob-symbol', text: knob.symbol }),
      createElement('span', { text: knob.label }),
    ]);

    const rowHeader = createElement('div', { className: 'knob-header' }, [
      labelEl,
      valueEl,
    ]);

    const slider = createElement('input', {
      type: 'range',
      className: 'knob-slider',
      attrs: {
        min: 0,
        max: 100,
        value: initialValue,
        'aria-label': knob.label,
      },
    });

    slider.addEventListener('input', (event) => {
      onKnobChange(knob.id, Number(event.target.value));
    });

    const row = createElement('div', { className: 'knob-row' }, [rowHeader, slider]);

    controlsById.set(knob.id, { slider, valueEl });
    list.append(row);
  }

  container.append(header, list);

  function update(knobsState, locked) {
    lockButton.textContent = locked ? 'Desbloquear' : 'Bloquear';
    lockButton.classList.toggle('btn-active', locked);
    lockButton.setAttribute('aria-pressed', String(locked));
    for (const [id, controls] of controlsById.entries()) {
      const val = knobsState[id];
      if (val == null) continue;
      controls.slider.disabled = locked;
      if (Number(controls.slider.value) !== val) {
        controls.slider.value = String(val);
      }
      controls.valueEl.textContent = `${val}%`;
    }
  }

  return { update };
}
