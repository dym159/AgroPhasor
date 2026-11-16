import { buildParcelSimulationMesh, buildPreviewMesh, shieldColor } from '../services/parcelSimulationMesh.js';
import { buildTerrainFromSatellite } from '../services/satelliteTerrainBuilder.js';
import { clearChildren, createElement } from '../utils/dom.js';

const INITIAL_YAW = -0.58;
const INITIAL_TILT = 0.56;

export function mountTerrainVisualizer(container, state, callbacks) {
  clearChildren(container);

  let yaw = INITIAL_YAW;
  let tilt = INITIAL_TILT;
  let offsetX = 0;
  let offsetY = 0;
  let drag = null;
  let result = null;
  let mesh = null;
  let previewMesh = null;
  let previewRequested = false;
  let disposed = false;
  let hour = 0;

  const status = createElement('span', { className: 'panel-tag', attrs: { role: 'status' } });
  const bareSoil = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Bare soil',
    onClick: callbacks.onToggleBareSoil,
  });
  const retry = createElement('button', {
    type: 'button',
    className: 'btn',
    text: 'Retry',
    onClick: callbacks.onRetrySimulation,
  });
  const toolbar = createElement('div', { className: 'stage-toolbar' }, [
    createElement('div', { className: 'stage-presets' }, [
      createElement('span', { className: 'parcel-bar-name', text: state.selectedParcel.name }),
      status,
    ]),
    createElement('div', { className: 'stage-presets' }, [
      retry,
      bareSoil,
      createElement('button', {
        type: 'button', className: 'btn', text: 'Change parcel', onClick: callbacks.onBackToMap,
      }),
      createElement('button', {
        type: 'button', className: 'btn btn-danger', text: 'Remove parcel', onClick: callbacks.onDeleteTerrain,
      }),
    ]),
  ]);

  const canvas = createElement('canvas', {
    className: 'terrain-canvas',
    attrs: { tabindex: 0, 'aria-label': '3D terrain. Use arrow keys to rotate.' },
  });
  const hourControl = createElement('input', { type: 'range', attrs: {
    min: 0, max: 23, value: 12, 'aria-label': 'Shield hour',
  } });
  hourControl.addEventListener('input', () => {
    hour = hourControl.valueAsNumber;
    drawScene();
  });
  const hourLabel = createElement('label', {}, ['Shield hour', hourControl]);
  toolbar.append(hourLabel);
  const context = canvas.getContext('2d');
  const legend = createElement('div', { className: 'terrain-legend' }, [
    createElement('div', {}, ['Shield · critical', createElement('span', { className: 'terrain-legend-shield' }), 'Optimal']),
    createElement('div', {}, ['Canopy · bare', createElement('span', { className: 'terrain-legend-canopy' }), 'Vigorous']),
    createElement('div', {}, ['Fertile soil', createElement('span', { className: 'terrain-legend-soil' }), 'Bedrock']),
  ]);
  const shieldStatus = createElement('div', { className: 'terrain-legend', attrs: { role: 'status' } });
  const view = createElement('div', { className: 'terrain-canvas-wrap' }, [
    canvas,
    legend,
    shieldStatus,
  ]);
  const diagnostics = createElement('p', { className: 'terrain-diagnostics', attrs: { role: 'status' } });
  view.append(diagnostics);
  const body = createElement('div', { className: 'stage-body terrain-stage-body' }, [view]);
  container.append(toolbar, body);

  const resizeObserver = new ResizeObserver(() => {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(view.clientWidth * dpr));
    canvas.height = Math.max(1, Math.round(view.clientHeight * dpr));
    drawScene();
  });
  resizeObserver.observe(view);

  canvas.addEventListener('pointerdown', (event) => {
    if (drag || event.button !== 0) return;
    drag = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      distance: 0,
      pan: event.shiftKey,
    };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (drag?.id !== event.pointerId) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    drag.distance += Math.hypot(dx, dy);
    drag.x = event.clientX;
    drag.y = event.clientY;
    if (drag.distance > 4) moveView(dx, dy, drag.pan);
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    canvas.addEventListener(event, ({ pointerId }) => {
      if (drag?.id === pointerId) drag = null;
    });
  }
  canvas.addEventListener('keydown', (event) => {
    const step = {
      ArrowLeft: [-24, 0], ArrowRight: [24, 0], ArrowUp: [0, -24], ArrowDown: [0, 24],
    }[event.key];
    if (!step) return;
    event.preventDefault();
    moveView(step[0], step[1], event.shiftKey);
  });

  function moveView(dx, dy, pan) {
    if (pan) {
      offsetX += dx;
      offsetY += dy;
    } else {
      yaw = (yaw + dx * 0.008) % (2 * Math.PI);
      tilt = Math.max(0.25, Math.min(Math.PI / 2, tilt - dy * 0.006));
    }
    drawScene();
  }

  function drawScene() {
    const width = view.clientWidth;
    const height = view.clientHeight;
    if (!context || !width || !height) return;

    context.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
    context.clearRect(0, 0, width, height);
    const surface = mesh ?? previewMesh;
    if (!surface) return;

    const scale = Math.min(width, height) * 0.40;
    const centerX = width * 0.5 + offsetX;
    const centerY = height * 0.53 + offsetY;
    const cosYaw = Math.cos(yaw);
    const sinYaw = Math.sin(yaw);
    const sinTilt = Math.sin(tilt);
    const cosTilt = Math.cos(tilt);
    const depth = ([x, y]) => x * sinYaw + y * cosYaw;
    const project = ([x, y], z) => ({
      x: centerX + (x * cosYaw - y * sinYaw) * scale,
      y: centerY + (depth([x, y]) * sinTilt - z * cosTilt) * scale,
    });
    const sorted = [...surface.cells].sort((a, b) => depth(a.center) - depth(b.center));
    for (const { cell, polygons, z, color } of sorted) {
      const erosionMm = cell?.accumulated_erosion_mm ?? 0;
      const seasonalSink = erosionMm > 0 && erosionMm < 20
        ? Math.min(0.085, erosionMm * 0.045)
        : 0;
      const canopyLift = cell?.shield_enabled && cell?.biomass_t_ha > 0
        ? Math.min(0.045, cell.biomass_t_ha * 0.0038)
        : 0;
      const cellZ = z - seasonalSink + canopyLift;
      const sideRgb = cell?.base_soil_color_rgb;
      const sideColor = Array.isArray(sideRgb) && sideRgb.length === 3
        ? `rgb(${Math.round(sideRgb[0] * 0.62)},${Math.round(sideRgb[1] * 0.62)},${Math.round(sideRgb[2] * 0.62)})`
        : '#3a302b';

      for (const rings of polygons) {
        const path = new Path2D();
        for (const [index, ring] of rings.entries()) {
          const top = ring.map((vertex) => project(vertex, cellZ));
          const bottom = ring.map((vertex) => project(vertex, surface.floor));
          drawCellSides(context, top, bottom, index > 0, sideColor);
          traceRing(path, top);
        }
        context.fillStyle = color;
        context.fill(path, 'evenodd');
        context.strokeStyle = 'rgba(214, 194, 167, 0.35)';
        context.lineWidth = 1;
        context.stroke(path);
      }
    }

    const shieldCells = sorted.filter(({ cell }) => cell?.shield_enabled);
    if (!shieldCells.length) return;

    for (const { cell, center, polygons, z } of shieldCells) {
      const envIndex = Math.max(
        0,
        Math.min(1, cell.hourly_shield_score?.[hour] ?? cell.hourly_environmental_index?.[hour] ?? cell.shield_score ?? 0)
      );
      const color = shieldColor(envIndex);
      const cellShieldZ = z + 0.055;

      // 1. Protective shield covering each cell's geometry
      for (const rings of polygons) {
        const shieldPoly = new Path2D();
        for (const ring of rings) {
          const topShield = ring.map((vertex) => project(vertex, cellShieldZ));
          traceRing(shieldPoly, topShield);
        }
        context.fillStyle = color;
        context.globalAlpha = 0.20 + 0.20 * envIndex;
        context.fill(shieldPoly, 'evenodd');
        context.globalAlpha = 0.85;
        context.strokeStyle = color;
        context.lineWidth = 1.4;
        context.stroke(shieldPoly);
      }
      context.globalAlpha = 1;

      // 2. Lissajous curve centered inside the cell shield
      const air = cell.hourly_air_temps;
      const canopy = cell.hourly_canopy_temps;
      if (!air?.length || canopy?.length !== air.length) continue;
      const meanAir = air.reduce((sum, value) => sum + value, 0) / air.length;
      const meanCanopy = canopy.reduce((sum, value) => sum + value, 0) / canopy.length;
      const ampAir = Math.max(2.5, ...air.map((value) => Math.abs(value - meanAir)));
      const ampDiff = Math.max(
        1.5,
        ...air.map((value, idx) => Math.abs((canopy[idx] - meanCanopy) - (value - meanAir)))
      );
      const vertices = polygons.flat(2);
      const spanX = Math.max(...vertices.map(([x]) => x)) - Math.min(...vertices.map(([x]) => x));
      const spanY = Math.max(...vertices.map(([, y]) => y)) - Math.min(...vertices.map(([, y]) => y));
      const radius = Math.min(spanX, spanY) * 0.34;
      // Minor semi-axis reflects the Lissajous buffering area while keeping visual legibility
      const minorRatio = 0.28 + 0.62 * envIndex;
      const trajectory = air.map((value, index) => {
        const phase = (2 * Math.PI * index) / air.length;
        const uNorm = Math.max(-1, Math.min(1, (value - meanAir) / ampAir));
        const diffNorm = Math.max(-1, Math.min(1, ((canopy[index] - meanCanopy) - (value - meanAir)) / ampDiff));
        const vNorm = Math.max(-1, Math.min(1, 0.35 * diffNorm + 0.65 * Math.cos(phase))) * minorRatio;
        const dx = (uNorm * cosYaw + vNorm * sinYaw) * radius;
        const dy = (-uNorm * sinYaw + vNorm * cosYaw) * radius;
        return project([center[0] + dx, center[1] + dy], cellShieldZ + 0.008);
      });
      const path = new Path2D();
      traceRing(path, trajectory);
      path.closePath();
      context.fillStyle = color;
      context.globalAlpha = 0.32;
      context.fill(path);
      context.globalAlpha = 1;
      context.strokeStyle = color;
      context.lineWidth = 1.6;
      context.stroke(path);
      const point = trajectory[Math.min(hour, trajectory.length - 1)];
      context.beginPath();
      context.arc(point.x, point.y, 2.4, 0, Math.PI * 2);
      context.fill();
    }
  }

  function update(nextState) {
    status.textContent = nextState.parcelSimulationStatusText;
    const simulation = nextState.parcelSimulationResult;
    diagnostics.hidden = !simulation;
    if (simulation) {
      const water = simulation.irrigation_alert
        ? `Suggested irrigation · ${Number(simulation.suggested_irrigation_mm).toFixed(1)} mm`
        : 'Soil moisture above irrigation threshold';
      const fertility = Number(simulation.lot_mean_eta_nutrientes);
      const erosionMm = simulation.lot_mean_accumulated_erosion_mm != null
        ? Number(simulation.lot_mean_accumulated_erosion_mm)
        : Math.max(0, 400 - Number(simulation.lot_mean_h_mm ?? 400));
      const planStats = simulation.plan_simulation
        ? `Biomass ${Number(simulation.lot_mean_biomass_t_ha ?? 0).toFixed(1)} t/ha (${Math.round(simulation.lot_mean_canopy_cover_pct ?? 0)}% cover) · W ${Number(simulation.lot_mean_soil_water_mm ?? 0).toFixed(0)} mm · Erosion ${erosionMm.toFixed(2)} mm · `
        : '';
      const forecastTag = simulation.montecarlo_confidence_pct != null
        ? ` · MC confidence ${simulation.montecarlo_confidence_pct}% (${simulation.climate_forecast?.mc_scenarios ?? ''} scenarios)`
        : simulation.plan_simulation ? ` · ${simulation.climate_source || 'Plan scenario'}` : '';
      diagnostics.textContent = `${planStats}${water} · Nutrient sufficiency ${Math.round(fertility * 100)}%${forecastTag}`;
    }
    retry.hidden = !nextState.parcelSimulationFailed;
    bareSoil.classList.toggle('btn-active', nextState.isBareSoil);
    bareSoil.setAttribute('aria-pressed', String(nextState.isBareSoil));
    const hasShield = nextState.parcelSimulationResult?.cells.some((cell) => cell.shield_enabled);
    shieldStatus.hidden = Boolean(hasShield);
    shieldStatus.textContent = nextState.isBareSoil
      ? 'Bare soil · thermal shield disabled'
      : nextState.parcelSimulationResult?.phase === 'transicion'
      ? 'Fallow / crop residue transition · canopy shield inactive'
      : nextState.parcelSimulationFailed || nextState.parcelSimulationResult ? 'Thermal shield unavailable'
      : 'Computing thermal shield…';
    if (!nextState.parcelSimulationResult && !previewRequested) {
      previewRequested = true;
      buildTerrainFromSatellite(nextState.selectedParcel).then((model) => {
        if (disposed) return;
        previewMesh = buildPreviewMesh(model);
        if (!mesh) drawScene();
      }).catch(() => {});
    }
    if (result === nextState.parcelSimulationResult) return;

    result = nextState.parcelSimulationResult;
    mesh = result ? buildParcelSimulationMesh(nextState.selectedParcel, result.cells) : null;
    hour = result ? Math.min(hourControl.valueAsNumber || 12, result.timestamps.length - 1) : 0;
    legend.hidden = !result;
    legend.firstElementChild.hidden = !hasShield;
    shieldStatus.classList.toggle('terrain-legend-offset', Boolean(result && !hasShield));
    drawScene();
  }

  legend.hidden = true;
  update(state);
  return {
    update,
    destroy: () => {
      disposed = true;
      resizeObserver.disconnect();
    },
  };
}

function traceRing(path, ring) {
  const [first, ...rest] = ring;
  path.moveTo(first.x, first.y);
  for (const point of rest) path.lineTo(point.x, point.y);
  path.closePath();
}

function drawCellSides(context, top, bottom, isHole, sideColor = '#3a302b') {
  let signedArea = 0;
  for (let i = 0; i < top.length; i++) {
    const a = top[i];
    const b = top[(i + 1) % top.length];
    signedArea += a.x * b.y - a.y * b.x;
  }
  const sign = Math.sign(signedArea) * (isHole ? -1 : 1);
  context.fillStyle = sideColor;
  for (let i = 0; i < top.length; i++) {
    const next = (i + 1) % top.length;
    if ((top[next].x - top[i].x) * sign >= 0) continue;
    const face = new Path2D();
    traceRing(face, [top[i], top[next], bottom[next], bottom[i]]);
    context.fill(face);
  }
}
