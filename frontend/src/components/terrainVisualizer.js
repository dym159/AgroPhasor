import { VISUAL_CROPS } from '../data/mockVisualData.js';
import { buildTerrainFromSatellite, normalizeParcelBoundary } from '../services/satelliteTerrainBuilder.js';
import { clearChildren, createElement } from '../utils/dom.js';

const GRID_ROWS = 6;
const GRID_COLS = 8;
const HALF_WIDTH = 0.9;
const HALF_DEPTH = 0.65;
const INITIAL_YAW = -0.58;
const INITIAL_TILT = 0.5;

export function mountTerrainVisualizer(container, state, callbacks) {
  if (!container) return { update: () => {}, destroy: () => {} };

  clearChildren(container);

  const boundary = splitBoundaryByCell(normalizeParcelBoundary(state.selectedParcel.polygon));
  let currentCrop = findCrop(state.previewCropId);
  let yawAngle = INITIAL_YAW;
  let tiltAngle = INITIAL_TILT;
  let offsetX = 0;
  let offsetY = 0;
  let panEnabled = false;
  let drag = null;
  let isDisposed = false;
  let terrainModel = null;
  let lastEdo1Result = state.edo1Result;
  let terrainLoadId = 0;

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

  const canvas = createElement('canvas', {
    className: 'terrain-canvas',
    attrs: { tabindex: 0, 'aria-label': 'Vista 3D del terreno. Usa las flechas para girar o desplazar.' },
  });

  const panButton = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Desplazar',
    attrs: { 'aria-pressed': false },
    onClick: () => {
      panEnabled = !panEnabled;
      panButton.setAttribute('aria-pressed', String(panEnabled));
      panButton.classList.toggle('btn-active', panEnabled);
    },
  });
  const resetButton = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Restablecer vista',
    onClick: () => {
      yawAngle = INITIAL_YAW;
      tiltAngle = INITIAL_TILT;
      offsetX = 0;
      offsetY = 0;
      drawScene();
    },
  });
  const viewControls = createElement('div', { className: 'terrain-view-controls' }, [
    panButton, resetButton,
  ]);
  const canvasWrap = createElement('div', { className: 'terrain-canvas-wrap' }, [
    canvas, viewControls,
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
    if (drag || event.button !== 0) return;
    drag = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      pan: panEnabled || event.shiftKey,
    };
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener('pointermove', (event) => {
    if (drag?.id !== event.pointerId) return;
    moveView(event.clientX - drag.x, event.clientY - drag.y, drag.pan);
    drag.x = event.clientX;
    drag.y = event.clientY;
  });

  const stopDragging = (event) => {
    if (drag?.id === event.pointerId) drag = null;
  };
  canvas.addEventListener('pointerup', stopDragging);
  canvas.addEventListener('pointercancel', stopDragging);
  canvas.addEventListener('lostpointercapture', stopDragging);
  canvas.addEventListener('keydown', (event) => {
    const step = {
      ArrowLeft: [-24, 0], ArrowRight: [24, 0], ArrowUp: [0, -24], ArrowDown: [0, 24],
    }[event.key];
    if (!step) return;
    event.preventDefault();
    moveView(step[0], step[1], panEnabled || event.shiftKey);
  });

  function moveView(dx, dy, pan) {
    if (pan) {
      offsetX += dx;
      offsetY += dy;
    } else {
      yawAngle = (yawAngle + dx * 0.008) % (2 * Math.PI);
      tiltAngle = clamp(tiltAngle - dy * 0.006, 0.18, Math.PI / 2);
    }
    drawScene();
  }

  syncCanvasSize(canvas, canvasWrap);
  drawScene();
  loadSatelliteTerrain(state.selectedParcel, state.edo1Result);

  async function loadSatelliteTerrain(parcel, edo1Result) {
    const loadId = ++terrainLoadId;
    const built = await buildTerrainFromSatellite(
      parcel,
      GRID_ROWS,
      GRID_COLS,
      edo1Result
    );
    if (isDisposed || loadId !== terrainLoadId) return;

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

    const centerX = width * 0.5 + offsetX;
    const centerY = height * 0.57 + offsetY;
    const scale = Math.min(width, height) * 0.42;
    const cosYaw = Math.cos(yawAngle);
    const sinYaw = Math.sin(yawAngle);
    const sinTilt = Math.sin(tiltAngle);
    const cosTilt = Math.cos(tiltAngle);

    const project = (nx, ny, nz) => {
      const rx = nx * cosYaw - ny * sinYaw;
      const ry = nx * sinYaw + ny * cosYaw;
      return {
        x: centerX + rx * scale,
        y: centerY + (ry * sinTilt - nz * cosTilt) * scale,
      };
    };

    drawExtrudedBox(context, project, {
      x1: -HALF_WIDTH,
      y1: -HALF_DEPTH,
      x2: HALF_WIDTH,
      y2: HALF_DEPTH,
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

    if (terrainModel) drawCrops(context, project, currentCrop.tint, terrainModel);
    drawSpatialGrid(context, project);
    drawParcelBoundary(context, project, boundary, terrainModel);
  }

  function update(nextState) {
    currentCrop = findCrop(nextState.previewCropId);
    if (nextState.edo1Result !== lastEdo1Result) {
      lastEdo1Result = nextState.edo1Result;
      loadSatelliteTerrain(nextState.selectedParcel, nextState.edo1Result);
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
  const dx = (2 * HALF_WIDTH) / cols;
  const dy = (2 * HALF_DEPTH) / rows;

  const cellsToDraw = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const idx = r * cols + c;
      if (gridPoints[idx] && !gridPoints[idx].insidePolygon) continue;

      const x1 = -HALF_WIDTH + c * dx;
      const y1 = -HALF_DEPTH + r * dy;
      const x2 = x1 + dx;
      const y2 = y1 + dy;
      const zTop = normalizedHeights[idx] || 0;
      const centerScreen = project((x1 + x2) * 0.5, (y1 + y2) * 0.5, 0);

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
  const dx = (2 * HALF_WIDTH) / GRID_COLS;
  const dy = (2 * HALF_DEPTH) / GRID_ROWS;

  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < GRID_COLS; c++) {
      const idx = r * GRID_COLS + c;
      if (model?.gridPoints?.[idx] && !model.gridPoints[idx].insidePolygon) {
        continue;
      }

      const nx = -HALF_WIDTH + (c + 0.5) * dx;
      const ny = -HALF_DEPTH + (r + 0.5) * dy;
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
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.26)';
  ctx.lineWidth = 1;

  for (let c = 0; c <= GRID_COLS; c++) {
    const nx = -HALF_WIDTH + (c / GRID_COLS) * (2 * HALF_WIDTH);
    const start = project(nx, -HALF_DEPTH, gridZ);
    const end = project(nx, HALF_DEPTH, gridZ);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }

  for (let r = 0; r <= GRID_ROWS; r++) {
    const ny = -HALF_DEPTH + (r / GRID_ROWS) * (2 * HALF_DEPTH);
    const start = project(-HALF_WIDTH, ny, gridZ);
    const end = project(HALF_WIDTH, ny, gridZ);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }
}

function splitBoundaryByCell(points) {
  const segments = [];
  for (let i = 0; i < points.length; i++) {
    const start = points[i];
    const end = points[(i + 1) % points.length];
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    if (dx === 0 && dy === 0) continue;

    const crossings = new Set([0, 1]);
    for (const [origin, delta, cells] of [[start.x, dx, GRID_COLS], [start.y, dy, GRID_ROWS]]) {
      if (!delta) continue;
      for (let line = 1; line < cells; line++) {
        const t = (line / cells - origin) / delta;
        if (t > 0 && t < 1) crossings.add(t);
      }
    }
    const stops = [...crossings].sort((a, b) => a - b);
    for (let j = 1; j < stops.length; j++) {
      const from = stops[j - 1];
      const to = stops[j];
      const midpoint = (from + to) / 2;
      const col = clamp(Math.floor((start.x + dx * midpoint) * GRID_COLS), 0, GRID_COLS - 1);
      const row = clamp(Math.floor((start.y + dy * midpoint) * GRID_ROWS), 0, GRID_ROWS - 1);
      segments.push({
        cell: row * GRID_COLS + col,
        x1: (2 * (start.x + dx * from) - 1) * HALF_WIDTH,
        y1: (2 * (start.y + dy * from) - 1) * HALF_DEPTH,
        x2: (2 * (start.x + dx * to) - 1) * HALF_WIDTH,
        y2: (2 * (start.y + dy * to) - 1) * HALF_DEPTH,
      });
    }
  }
  return segments;
}

function drawParcelBoundary(ctx, project, segments, model) {
  if (!segments.length) return;
  ctx.save();
  ctx.beginPath();
  for (const [index, { cell, x1, y1, x2, y2 }] of segments.entries()) {
    const height = model?.gridPoints[cell]?.insidePolygon ? model.normalizedHeights[cell] : 0;
    const start = project(x1, y1, height);
    const end = project(x2, y2, height);
    if (index === 0) ctx.moveTo(start.x, start.y);
    else ctx.lineTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
  }
  ctx.closePath();
  ctx.lineJoin = 'round';
  ctx.strokeStyle = '#11283a';
  ctx.lineWidth = 5;
  ctx.stroke();
  ctx.strokeStyle = '#7dd3fc';
  ctx.lineWidth = 2.5;
  ctx.stroke();
  ctx.restore();
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
