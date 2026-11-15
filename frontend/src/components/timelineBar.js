import { TIMELINE_MONTHS } from '../data/mockVisualData.js';
import { clearChildren, createElement } from '../utils/dom.js';

export function createTimelineBar(container, initialState, callbacks) {
  if (!container) return { update: () => {} };

  clearChildren(container);

  const ticksRow = createElement('div', { className: 'timeline-ticks' });
  const tickButtons = TIMELINE_MONTHS.map((month, index) => {
    const btn = createElement('button', {
      type: 'button',
      className: 'month-tick',
      text: month,
      onClick: () => callbacks.onChangeMonth(index),
    });
    ticksRow.append(btn);
    return btn;
  });

  const slider = createElement('input', {
    type: 'range',
    className: 'timeline-slider',
    attrs: {
      min: 0,
      max: TIMELINE_MONTHS.length - 1,
      value: initialState.activeMonthIndex,
      'aria-label': 'Mes activo de la línea de tiempo',
    },
  });

  slider.addEventListener('input', (event) => {
    callbacks.onChangeMonth(Number(event.target.value));
  });

  const periodLabel = createElement('span', { className: 'timeline-period-label' });
  const addPeriodBtn = createElement('button', {
    type: 'button',
    className: 'btn btn-compact',
    text: '+ Periodo',
    onClick: callbacks.onAddPeriod,
  });

  const bottomRow = createElement('div', { className: 'timeline-bottom' }, [
    periodLabel,
    addPeriodBtn,
  ]);

  container.append(ticksRow, slider, bottomRow);

  function update(state) {
    const activeMonth = TIMELINE_MONTHS[state.activeMonthIndex] ?? TIMELINE_MONTHS[0];
    periodLabel.textContent = `${activeMonth} · ${state.periodCount} periodos`;

    if (Number(slider.value) !== state.activeMonthIndex) {
      slider.value = String(state.activeMonthIndex);
    }

    tickButtons.forEach((btn, index) => {
      btn.classList.toggle('is-active', index === state.activeMonthIndex);
    });
  }

  update(initialState);
  return { update };
}
