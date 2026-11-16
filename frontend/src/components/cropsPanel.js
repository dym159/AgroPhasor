import { CROP_DRAG_TYPE, CROP_GROUPS, VISUAL_CROPS } from '../data/mockVisualData.js';
import { clearChildren, createElement } from '../utils/dom.js';

export function createCropsPanel(container, initialState, callbacks) {
  if (!container) return { update: () => {} };

  clearChildren(container);

  const countTag = createElement('span', { className: 'panel-tag' });
  const header = createElement('div', { className: 'panel-header' }, [
    createElement('h2', { className: 'panel-title', text: 'Crops' }),
    countTag,
  ]);

  const searchInput = createElement('input', {
    type: 'search',
    className: 'crop-search-input',
    attrs: {
      placeholder: 'Filter crops...',
      value: initialState.cropSearchQuery,
    },
  });

  searchInput.addEventListener('input', (event) => {
    callbacks.onSearchCrop(event.target.value);
  });

  const groupRow = createElement('div', { className: 'crop-group-tabs' });
  const bulkActions = createElement('div', { className: 'crop-bulk-bar' });
  const list = createElement('div', { className: 'crops-list panel-scroll' });

  container.append(header, searchInput, groupRow, bulkActions, list);

  function update(state) {
    const filteredCrops = filterCrops(
      VISUAL_CROPS,
      state.activeCropGroup,
      state.cropSearchQuery
    );

    countTag.textContent = `${state.selectedCropIds.length} active`;

    clearChildren(groupRow);
    for (const groupName of CROP_GROUPS) {
      const isActive = state.activeCropGroup === groupName;
      groupRow.append(
        createElement('button', {
          type: 'button',
          className: `branch-chip ${isActive ? 'is-selected' : ''}`,
          text: groupName,
          onClick: () => callbacks.onSelectGroup(groupName),
        })
      );
    }

    clearChildren(bulkActions);
    const selectVisibleBtn = createElement('button', {
      type: 'button',
      className: 'btn btn-compact',
      text: 'Select visible',
      onClick: () => callbacks.onSelectBatch(filteredCrops.map((c) => c.id)),
    });
    const clearAllBtn = createElement('button', {
      type: 'button',
      className: 'btn btn-compact',
      text: 'Clear',
      onClick: callbacks.onClearCrops,
    });
    bulkActions.append(selectVisibleBtn, clearAllBtn);

    clearChildren(list);
    for (const crop of filteredCrops) {
      const isSelected = state.selectedCropIds.includes(crop.id);
      const swatch = createElement('span', {
        className: 'crop-swatch',
        style: { backgroundColor: crop.tint },
      });

      const itemBtn = createElement(
        'button',
        {
          type: 'button',
          className: `crop-row ${isSelected ? 'is-selected' : ''}`,
          attrs: { draggable: 'true' },
          onClick: () => callbacks.onToggleCrop(crop.id),
        },
        [
          swatch,
          createElement('span', { className: 'crop-name', text: crop.name }),
        ]
      );

      itemBtn.addEventListener('dragstart', (event) => {
        event.dataTransfer.setData(CROP_DRAG_TYPE, crop.id);
        event.dataTransfer.effectAllowed = 'copy';
      });
      list.append(itemBtn);
    }
  }

  update(initialState);
  return { update };
}

function filterCrops(crops, group, query) {
  const normalizedQuery = query.trim().toLowerCase();
  return crops.filter((crop) => {
    const matchesGroup = group === 'All' || crop.group === group;
    if (!matchesGroup) return false;
    if (!normalizedQuery) return true;
    return (
      crop.name.toLowerCase().includes(normalizedQuery) ||
      crop.group.toLowerCase().includes(normalizedQuery)
    );
  });
}
