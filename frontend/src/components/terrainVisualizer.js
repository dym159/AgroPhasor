import { VISUAL_CROPS } from '../data/mockVisualData.js';
import { buildTerrainFromSatellite } from '../services/satelliteTerrainBuilder.js';
import { clearChildren, createElement } from '../utils/dom.js';

const GRID_ROWS = 6;
const GRID_COLS = 8;

export function mountTerrainVisualizer(container, state, callbacks) {
  if (!container) return { update: () => {}, destroy: () => {} };

  clearChildren(container);

  let currentCrop = findCrop(state.previewCropId);
  let yawAngle = -0.58;
  let isDragging = false;
  let lastPointerX = 0;
  let isDisposed = false;
  let terrainModel = null;
  let lastEdo1Count = state.edo1Result?.cells?.length ?? 0;

  const variationBadge = createElement('span', {
    className: 'panel-tag',
    text: 'Muestreando relieve SRTM + satélite...',
  });

  const deleteTerrainBtn = createElement('button', {
    type: 'button',
    className: 'btn btn-danger',
    text: 'Eliminar terreno',
    onClick: callbacks.onDeleteTerrain,
  });

  const changeTerrainBtn = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Cambiar terreno',
    onClick: callbacks.onBackToMap,
  });

  const toolbar = createElement('div', { className: 'stage-toolbar' }, [
    createElement('div', { className: 'stage-presets' }, [
      createElement('span', {
        className: 'parcel-bar-name',
        text: state.selectedParcel.name,
      }),
      variationBadge,
    ]),
    createElement('div', { className: 'stage-presets' }, [
      deleteTerrainBtn,
      changeTerrainBtn,
    ]),
  ]);

  const canvas = createElement('canvas', { className: 'terrain-canvas' });
  const canvasWrap = createElement('div', { className: 'terrain-canvas-wrap' }, [
    canvas,
  ]);

  const body = createElement('div', { className: 'stage-body' }, [canvasWrap]);
  container.append(toolbar, body);

  const context = canvas.getContext('2d');
  if (!context) return { update: () => {}, destroy: () => {} };

  const resizeObserver = new ResizeObserver(() => {
    syncCanvasSize(canvas, canvasWrap);
    drawScene();
  });
  resizeObserver.observe(canvasWrap);

  canvas.addEventListener('pointerdown', (event) => {
    isDragging = true;
    lastPointerX = event.clientX;
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener('pointermove', (event) => {
    if (!isDragging) return;
    const deltaX = event.clientX - lastPointerX;
    lastPointerX = event.clientX;
    yawAngle = clamp(yawAngle + deltaX * 0.008, -1.25, -0.15);
    drawScene();
  });

  const stopDragging = () => {
    isDragging = false;
  };
  canvas.addEventListener('pointerup', stopDragging);
  canvas.addEventListener('pointercancel', stopDragging);

  syncCanvasSize(canvas, canvasWrap);
  loadSatelliteTerrain(state.selectedParcel, state.edo1Result);

  async function loadSatelliteTerrain(parcel, edo1Result) {
    const built = await buildTerrainFromSatellite(
      parcel,
      GRID_ROWS,
      GRID_COLS,
      edo1Result
    );
    if (isDisposed) return;

    terrainModel = built;
    const tempSuffix =
      built.lotMeanTemp != null ? ` · Dosel ${built.lotMeanTemp} °C` : '';
    variationBadge.textContent = built.hasVariation
      ? `${built.sourceLabel}: +${built.deltaMeters} m (${built.minElevation}–${built.maxElevation} m)${tempSuffix}`
      : `${built.sourceLabel}: Sin variación (${built.deltaMeters} m · Plano)${tempSuffix}`;

    drawScene();
  }

  function drawScene() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;

    const dpr = window.devicePixelRatio || 1;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);

    const centerX = width * 0.5;
    const centerY = height * 0.57;
    const scale = Math.min(width, height) * 0.42;

    const project = (nx, ny, nz) => {
      const cosA = Math.cos(yawAngle);
      const sinA = Math.sin(yawAngle);
      const rx = nx * cosA - ny * sinA;
      const ry = nx * sinA + ny * cosA;
      return {
        x: centerX + rx * scale,
        y: centerY + ry * scale * 0.48 - nz * scale * 0.65,
      };
    };

    drawExtrudedBox(context, project, {
      x1: -0.9,
      y1: -0.65,
      x2: 0.9,
      y2: 0.65,
      zBottom: -0.2,
      zTop: 0,
      topColor: '#2c4730',
      topStroke: '#526375',
      sideColors: ['#5c3b21', '#422917'],
      sideStroke: '#7c5130',
    });

    if (terrainModel) {
      drawSatelliteCells(context, project, terrainModel);
    }

    drawCrops(context, project, currentCrop.tint, terrainModel);
    drawSpatialGrid(context, project);
  }

  function update(nextState) {
    currentCrop = findCrop(nextState.previewCropId);
    const nextEdo1Count = nextState.edo1Result?.cells?.length ?? 0;
    if (nextEdo1Count !== lastEdo1Count) {
      lastEdo1Count = nextEdo1Count;
      loadSatelliteTerrain(nextState.selectedParcel, nextState.edo1Result);
      return;
    }
    drawScene();
  }

  return {
    update,
    destroy: () => {
      isDisposed = true;
      resizeObserver.disconnect();
    },
  };
}

function drawSatelliteCells(ctx, project, model) {
  const { rows, cols, normalizedHeights, cellColors, gridPoints } = model;
  const dx = 1.8 / cols;
  const dy = 1.3 / rows;

  const cellsToDraw = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const idx = r * cols + c;
      if (gridPoints[idx] && !gridPoints[idx].insidePolygon) continue;

      const x1 = -0.9 + c * dx;
      const y1 = -0.65 + r * dy;
      const x2 = x1 + dx;
      const y2 = y1 + dy;
      const zTop = normalizedHeights[idx] || 0;
      const centerScreen = project((x1 + x2) * 0.5, (y1 + y2) * 0.5, zTop);

      cellsToDraw.push({
        x1,
        y1,
        x2,
        y2,
        zTop,
        color: cellColors[idx] ?? '#325136',
        screenY: centerScreen.y,
      });
    }
  }

  cellsToDraw.sort((a, b) => a.screenY - b.screenY);

  for (const cell of cellsToDraw) {
    if (cell.zTop > 0.005) {
      drawExtrudedBox(ctx, project, {
        x1: cell.x1,
        y1: cell.y1,
        x2: cell.x2,
        y2: cell.y2,
        zBottom: 0,
        zTop: cell.zTop,
        topColor: cell.color,
        topStroke: 'rgba(148, 163, 184, 0.35)',
        sideColors: ['#6b472b', '#4e331e'],
        sideStroke: 'rgba(255, 255, 255, 0.16)',
      });
    } else {
      const quad = [
        project(cell.x1, cell.y1, 0),
        project(cell.x2, cell.y1, 0),
        project(cell.x2, cell.y2, 0),
        project(cell.x1, cell.y2, 0),
      ];
      fillPolygon(ctx, quad, cell.color, 'rgba(148, 163, 184, 0.22)');
    }
  }
}

function drawExtrudedBox(ctx, project, box) {
  const top = [
    project(box.x1, box.y1, box.zTop),
    project(box.x2, box.y1, box.zTop),
    project(box.x2, box.y2, box.zTop),
    project(box.x1, box.y2, box.zTop),
  ];
  const base = [
    project(box.x1, box.y1, box.zBottom),
    project(box.x2, box.y1, box.zBottom),
    project(box.x2, box.y2, box.zBottom),
    project(box.x1, box.y2, box.zBottom),
  ];

  const sideFaces = [
    { quad: [top[0], top[1], base[1], base[0]], color: box.sideColors[1] },
    { quad: [top[1], top[2], base[2], base[1]], color: box.sideColors[0] },
    { quad: [top[2], top[3], base[3], base[2]], color: box.sideColors[1] },
    { quad: [top[3], top[0], base[0], base[3]], color: box.sideColors[0] },
  ];

  sideFaces.sort((a, b) => averageY(a.quad) - averageY(b.quad));
  for (const face of sideFaces.slice(2)) {
    fillPolygon(ctx, face.quad, face.color, box.sideStroke);
  }

  fillPolygon(ctx, top, box.topColor, box.topStroke);
}

function averageY(points) {
  return (points[0].y + points[1].y + points[2].y + points[3].y) / 4;
}

function drawCrops(ctx, project, tint, model) {
  const dx = 1.8 / GRID_COLS;
  const dy = 1.3 / GRID_ROWS;

  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < GRID_COLS; c++) {
      const idx = r * GRID_COLS + c;
      if (model?.gridPoints?.[idx] && !model.gridPoints[idx].insidePolygon) {
        continue;
      }

      const nx = -0.9 + (c + 0.5) * dx;
      const ny = -0.65 + (r + 0.5) * dy;
      const baseZ = model?.normalizedHeights?.[idx] || 0.01;
      const root = project(nx, ny, baseZ);
      const tip = project(nx, ny, baseZ + 0.14);

      ctx.strokeStyle = '#4ade80';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(root.x, root.y);
      ctx.lineTo(tip.x, tip.y);
      ctx.stroke();

      ctx.fillStyle = tint;
      ctx.beginPath();
      ctx.ellipse(tip.x - 3.5, tip.y + 2.5, 4, 2, -0.5, 0, Math.PI * 2);
      ctx.ellipse(tip.x + 3.5, tip.y + 2.5, 4, 2, 0.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function drawSpatialGrid(ctx, project) {
  const gridZ = 0.4;
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.52)';
  ctx.lineWidth = 1;

  for (let c = 0; c <= GRID_COLS; c++) {
    const nx = -0.9 + (c / GRID_COLS) * 1.8;
    const start = project(nx, -0.65, gridZ);
    const end = project(nx, 0.65, gridZ);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }

  for (let r = 0; r <= GRID_ROWS; r++) {
    const ny = -0.65 + (r / GRID_ROWS) * 1.3;
    const start = project(-0.9, ny, gridZ);
    const end = project(0.9, ny, gridZ);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }
}

function fillPolygon(ctx, points, fillColor, strokeColor) {
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 1;
  ctx.stroke();
}

function syncCanvasSize(canvas, wrapper) {
  const dpr = window.devicePixelRatio || 1;
  const width = wrapper.clientWidth;
  const height = wrapper.clientHeight;
  canvas.width = Math.max(1, Math.floor(width * dpr));
  canvas.height = Math.max(1, Math.floor(height * dpr));
}

function findCrop(cropId) {
  return VISUAL_CROPS.find((crop) => crop.id === cropId) ?? VISUAL_CROPS[0];
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
