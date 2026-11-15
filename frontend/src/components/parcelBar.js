import { clearChildren, createElement } from '../utils/dom.js';

export function renderParcelBar(container, state, callbacks) {
  if (!container) return;

  clearChildren(container);

  const { selectedParcel, centerMode, hasActiveTerrain, edo1Result } = state;
  const isTerrainView = centerMode === 'terrain';
  const titleText = hasActiveTerrain ? selectedParcel.name : 'Sin terreno seleccionado';

  const nameEl = createElement('span', {
    className: 'parcel-bar-name',
    text: titleText,
  });

  const infoChildren = [nameEl];
  if (hasActiveTerrain && edo1Result?.lot_mean_temp != null) {
    infoChildren.push(
      createElement('span', {
        className: 'panel-tag',
        text: `Dosel: ${edo1Result.lot_mean_temp} °C · ${edo1Result.cells_count} celdas SRTM`,
      })
    );
  }

  const infoWrap = createElement('div', { className: 'parcel-bar-info' }, infoChildren);

  const selectMapBtn = createElement('button', {
    type: 'button',
    className: `btn ${!isTerrainView ? 'btn-active' : ''}`,
    text: 'Mapa',
    onClick: () => callbacks.onChangeMode('select'),
  });

  const terrainViewBtn = createElement('button', {
    type: 'button',
    className: `btn ${isTerrainView ? 'btn-primary' : ''}`,
    text: 'Vista 3D',
    attrs: hasActiveTerrain ? {} : { disabled: 'true' },
    onClick: () => {
      if (!hasActiveTerrain) return;
      callbacks.onChangeMode('terrain');
    },
  });

  const deleteTerrainBtn = createElement('button', {
    type: 'button',
    className: 'btn btn-danger',
    text: 'Eliminar terreno',
    attrs: hasActiveTerrain ? {} : { disabled: 'true' },
    onClick: callbacks.onDeleteTerrain,
  });

  const actions = createElement('div', { className: 'parcel-bar-actions' }, [
    selectMapBtn,
    terrainViewBtn,
    deleteTerrainBtn,
  ]);

  container.append(infoWrap, actions);
}
