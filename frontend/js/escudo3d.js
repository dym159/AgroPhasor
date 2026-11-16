import { parcelFootprint } from './parcel-geometry.js';
import { metersPerWorldPixel, exaggerateRelief } from './terrain.js';

/**
 * AgroPhasor - 2.5D Isometric Viewer "Square Hills + Flat Shield"
 * Synchronized in real time with the physical model:
 * - Physical topsoil subsidence from erosion (H)
 * - Soil color transition: Fertile brown <-> Degraded rocky gray
 * - Canopy height driven by aboveground biomass (B)
 * - 4 Shield States:
 *     1. Cobalt Blue (Psi -> 1)
 *     2. Violet / Amber (Psi ~ 0.5)
 *     3. Deep Red (Psi -> 0)
 *     4. Shield Deactivated (q = Transition, bare soil)
 */

export class Escudo3DViewer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    // Synchronized physical state
    this.state = {
      W: 142.5,
      T: 16.8,
      H: 278,
      B: 11.8,
      erosionSinkingMm: 4.5,
      degradationFactor: 0.15,
      soilColor: {
        top: "rgb(38, 44, 28)",
        front: "rgb(28, 32, 20)",
        side: "rgb(18, 22, 14)",
        hex: "#262c1c"
      },
      eta_nutrientes: 0.78,
      limitingNutrient: "Nitrogen (N)",
      Psi: 0.85,
      shieldState: "azul_cobalto", // "azul_cobalto" | "violeta_ambar" | "rojo_intenso" | "desactivado"
      shieldColor: "#2563eb",
      shieldName: "Cobalt Blue (Optimal Resilience)",
      stage: "cultivo",
      cropName: "Canchan Potato"
    };

    // Isometric projection parameters
    this.angle = Math.PI / 6; // 30 degrees
    this.scale = 1.0;
    this.rotation = 0;
    this.animTime = 0;
    this.isDragging = false;
    this.lastMouseX = 0;

    this.initCanvas();
    this.bindInteractions();
    this.startAnimationLoop();
  }

  initCanvas() {
    const resize = () => {
      if (!this.canvas) return;
      const rect = this.canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      this.width = rect.width || 420;
      this.height = rect.height || 300;
      this.canvas.width = this.width * dpr;
      this.canvas.height = this.height * dpr;
      this.ctx.scale(dpr, dpr);
      this.scale = Math.min(this.width / 360, this.height / 270);
    };

    resize();
    window.addEventListener('resize', resize);
  }

  bindInteractions() {
    if (!this.canvas) return;

    const onDown = (clientX) => {
      this.isDragging = true;
      this.lastMouseX = clientX;
    };

    const onMove = (clientX) => {
      if (!this.isDragging) return;
      const delta = clientX - this.lastMouseX;
      this.rotation += delta * 0.008;
      this.lastMouseX = clientX;
    };

    const onUp = () => {
      this.isDragging = false;
    };

    this.canvas.addEventListener('mousedown', (e) => onDown(e.clientX));
    window.addEventListener('mousemove', (e) => onMove(e.clientX));
    window.addEventListener('mouseup', onUp);

    this.canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) onDown(e.touches[0].clientX);
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
      if (this.isDragging && e.touches.length === 1) onMove(e.touches[0].clientX);
    }, { passive: true });

    window.addEventListener('touchend', onUp);
  }

  /**
   * Update complete state from the physics engine
   */
  updatePhysicsState(physData) {
    if (!physData) return;
    Object.assign(this.state, physData);
    this.heightCache = new Map();
  }

  setParcelGeometry(geometry, zoom = 17) {
    this.footprint = parcelFootprint(geometry);
    this.gridZoom = zoom;
    this.heightCache = new Map();
    const f = this.footprint;
    const generation = this.terrainGeneration = (this.terrainGeneration || 0) + 1;
    const label = document.getElementById('terrain-status');
    if (!f || !this.terrain) {
      if (label) label.textContent = 'Select a parcel to view terrain relief';
      return;
    }
    if (label) label.textContent = 'Loading terrain elevation…';
    const pad = Math.max(f.width, f.height) / 16;
    this.terrain.loadBounds(f.minX - pad, f.minY - pad, f.minX + f.width + pad, f.minY + f.height + pad)
      .then(complete => {
        if (generation !== this.terrainGeneration) return;
        this.heightCache = new Map();
        if (label) label.textContent = complete
          ? 'Visual relief ×4 · simulated slope · baseline erosion ×250'
          : 'Elevation unavailable or incomplete · no synthetic relief generated';
      }).catch(() => {
        if (generation === this.terrainGeneration && label) label.textContent = 'Elevation unavailable';
      });
  }

  terrainOffset(x, y) {
    const f = this.footprint;
    if (!f || !this.terrain) return 0;
    this.heightCache ??= new Map();
    const key = x + ',' + y;
    if (this.heightCache.has(key)) return this.heightCache.get(key);
    const wx = f.minX + (x - f.offsetX) / f.scale, wy = f.minY + (y - f.offsetY) / f.scale;
    const cx = f.minX + f.width / 2, cy = f.minY + f.height / 2;
    const reference = this.terrain.sample(cx, cy);
    const height = this.terrain.height(wx, wy, 14, true);
    const result = reference === null || height === null ? 0
      : exaggerateRelief((height - reference) * f.scale / metersPerWorldPixel(cy));
    this.heightCache.set(key, result);
    return result;
  }

  terrainRing(ring) {
    const points = [];
    for (let i = 0; i < ring.length - 1; i++) {
      const a = ring[i], b = ring[i + 1];
      const segments = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 5));
      for (let j = 0; j < segments; j++) points.push([
        a[0] + (b[0] - a[0]) * j / segments, a[1] + (b[1] - a[1]) * j / segments]);
    }
    if (points.length) points.push(points[0]);
    return points;
  }

  parcelPath(ctx, ox, oy, z, followTerrain = true) {
    ctx.beginPath();
    for (const polygon of this.footprint.polygons) {
      for (const ring of polygon) {
        this.terrainRing(ring).forEach(([x, y], i) => {
          const p = this.isoProject(x, y, z, ox, oy, followTerrain);
          if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
        });
        ctx.closePath();
      }
    }
  }

  drawParcelGrid(ctx, ox, oy, z, color, followTerrain = true) {
    const f = this.footprint;
    const baseStep = 32 / 2 ** this.gridZoom;
    const step = baseStep * Math.max(1, Math.ceil(Math.max(f.width, f.height) / baseStep / 80));
    ctx.save();
    this.parcelPath(ctx, ox, oy, z, followTerrain);
    ctx.clip('evenodd');
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    // Same position and spacing as map cells, clipped to the parcel contour.
    const line = (x1, y1, x2, y2) => {
      const segments = Math.ceil(Math.hypot(x2 - x1, y2 - y1) / 4);
      for (let i = 0; i <= segments; i++) {
        const p = this.isoProject(x1 + (x2 - x1) * i / segments, y1 + (y2 - y1) * i / segments, z, ox, oy, followTerrain);
        if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
      }
    };
    for (let x = Math.ceil(f.minX / step) * step, n = 0; x <= f.minX + f.width && n < 2048; x += step, n++) {
      const px = f.offsetX + (x - f.minX) * f.scale;
      line(px, 0, px, 130);
    }
    for (let y = Math.ceil(f.minY / step) * step, n = 0; y <= f.minY + f.height && n < 2048; y += step, n++) {
      const py = f.offsetY + (y - f.minY) * f.scale;
      line(0, py, 190, py);
    }
    ctx.stroke();
    ctx.restore();
  }

  drawParcel(ctx, ox, oy, thickness, sinking, shieldZ) {
    const top = -sinking, bottom = top - thickness;
    const sides = [];
    for (const polygon of this.footprint.polygons) {
      for (const ring of polygon) {
        const edge = this.terrainRing(ring);
        for (let i = 0; i < edge.length - 1; i++) {
          const a = edge[i], b = edge[i + 1];
          sides.push({ points: [this.isoProject(...a, top, ox, oy), this.isoProject(...b, top, ox, oy),
            this.isoProject(...b, bottom, ox, oy), this.isoProject(...a, bottom, ox, oy)] });
        }
      }
    }
    sides.sort((a, b) => a.points[0].y + a.points[1].y - b.points[0].y - b.points[1].y);
    for (const side of sides) {
      ctx.beginPath();
      side.points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
      ctx.closePath(); ctx.fillStyle = this.state.soilColor.side;
      ctx.fill(); ctx.strokeStyle = this.state.soilColor.front; ctx.stroke();
    }
    this.parcelPath(ctx, ox, oy, top);
    ctx.fillStyle = this.state.soilColor.top; ctx.fill('evenodd');
    this.drawTerrainFacets(ctx, ox, oy, top);
    this.drawParcelGrid(ctx, ox, oy, top, 'rgba(225, 255, 248, 0.95)');
    ctx.save();
    this.parcelPath(ctx, ox, oy, top); ctx.clip('evenodd');
    if (this.state.stage !== 'transicion') this.drawCrops(ctx, ox, oy, thickness, 190, 130, sinking);
    else this.drawStubbleResidue(ctx, ox, oy, thickness, 190, 130, sinking);
    ctx.restore();
    const active = this.state.shieldState !== 'desactivado';
    ctx.save();
    ctx.strokeStyle = this.state.shieldColor;
    ctx.globalAlpha = active ? 0.35 : 0.15;
    for (const polygon of this.footprint.polygons) {
      for (const [x, y] of polygon[0].slice(0, -1)) {
        const a = this.isoProject(x, y, top, ox, oy), b = this.isoProject(x, y, shieldZ, ox, oy, false);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
    this.parcelPath(ctx, ox, oy, shieldZ, false);
    ctx.fillStyle = this.state.shieldColor; ctx.globalAlpha = active ? 0.10 : 0.04;
    ctx.fill('evenodd'); ctx.globalAlpha = active ? 0.9 : 0.35;
    ctx.lineWidth = 1.5; if (!active) ctx.setLineDash([4, 4]); ctx.stroke();
    ctx.restore();
    if (active) this.drawParcelGrid(ctx, ox, oy, shieldZ, this.state.shieldColor, false);
  }

  drawTerrainFacets(ctx, ox, oy, z) {
    ctx.save();
    this.parcelPath(ctx, ox, oy, z); ctx.clip('evenodd');
    const triangles = [];
    for (let x = 0; x < 190; x += 5) for (let y = 0; y < 130; y += 5) {
      const a = [x, y], b = [x + 5, y], c = [x + 5, y + 5], d = [x, y + 5];
      for (const vertices of [[a, b, c], [a, c, d]]) {
        const points = vertices.map(([vx, vy]) => this.isoProject(vx, vy, z, ox, oy));
        const dx = this.terrainOffset(x + 5, y) - this.terrainOffset(x, y);
        const dy = this.terrainOffset(x, y + 5) - this.terrainOffset(x, y);
        const f = this.footprint;
        const wx = f.minX + (x + 2.5 - f.offsetX) / f.scale;
        const wy = f.minY + (y + 2.5 - f.offsetY) / f.scale;
        const color = this.terrain?.visualColor(wx, wy, 0, 14, true) || this.state.soilColor.top;
        triangles.push({ points, color, light: Math.max(-0.5, Math.min(0.65, (dx + dy) / 9)) });
      }
    }
    triangles.sort((a, b) => a.points.reduce((v, p) => v + p.y, 0) - b.points.reduce((v, p) => v + p.y, 0));
    for (const {points, color, light} of triangles) {
      ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
      ctx.closePath(); ctx.fillStyle = color; ctx.fill();
      ctx.fillStyle = light < 0 ? 'rgba(226, 232, 240, ' + (-light) + ')' : 'rgba(0, 0, 0, ' + light + ')';
      ctx.fill();
    }
    ctx.restore();
  }

  // 3D -> 2D isometric projection with interactive rotation
  isoProject(x, y, z, originX, originY, followTerrain = true) {
    if (followTerrain) z += this.terrainOffset(x, y);
    // Block center
    const cx = x - 95;
    const cy = y - 65;
    const rx = cx * Math.cos(this.rotation) - cy * Math.sin(this.rotation);
    const ry = cx * Math.sin(this.rotation) + cy * Math.cos(this.rotation);

    const px = originX + (rx - ry) * Math.cos(this.angle) * this.scale;
    const py = originY + (rx + ry) * Math.sin(this.angle) * this.scale - (z * this.scale * 0.92);
    return { x: px, y: py };
  }

  render() {
    if (!this.ctx) return;
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    ctx.clearRect(0, 0, w, h);

    const originX = w * 0.5;
    const originY = h * 0.58;
    this.animTime += 0.025;

    // Square soil block dimensions
    const slabW = 190;
    const slabL = 130;
    
    // 1. SOIL SUBSIDENCE DUE TO EROSION
    // Higher erosion (erosionSinkingMm) sinks the substrate along the Z axis
    const visualSinkingZ = 0; // Erosion is already applied per vertex in TerrainSurface.
    const baseHeight = 26; // Visual slab thickness
    const effectiveSlabH = Math.max(8, baseHeight - visualSinkingZ);

    // 2. FLAT SHIELD HEIGHT
    // Depends on biomass B (canopy). During transition it drops close to the soil surface
    let shieldHeight = 75;
    if (this.state.stage === "transicion") {
      shieldHeight = 35; // Collapsed during fallow/bare soil
    } else {
      const biomassOffset = Math.min(25, (this.state.B || 10) * 1.5);
      shieldHeight = 55 + biomassOffset + Math.sin(this.animTime * 1.5) * 2;
    }

    if (!this.footprint) {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Select or draw a parcel on the map', originX, originY);
      return;
    }
    this.drawParcel(ctx, originX, originY, effectiveSlabH, visualSinkingZ, shieldHeight);

    // 6. TOP HUD AND LIVE SHIELD LABEL
    this.drawHUD(ctx, originX, originY, slabW, slabL, shieldHeight);
  }

  /**
   * 1. Square soil slab: Fertile brown <-> Rocky gray and subsidence
   */
  drawSquareSlab(ctx, ox, oy, sw, sl, sh, sinkingZ) {
    const topZ = -sinkingZ;
    const botZ = -sinkingZ - sh;

    // Lower vertices
    const b0 = this.isoProject(0, 0, botZ, ox, oy);
    const b1 = this.isoProject(sw, 0, botZ, ox, oy);
    const b2 = this.isoProject(sw, sl, botZ, ox, oy);
    const b3 = this.isoProject(0, sl, botZ, ox, oy);

    // Upper vertices (with subsidence)
    const t0 = this.isoProject(0, 0, topZ, ox, oy);
    const t1 = this.isoProject(sw, 0, topZ, ox, oy);
    const t2 = this.isoProject(sw, sl, topZ, ox, oy);
    const t3 = this.isoProject(0, sl, topZ, ox, oy);

    const soil = this.state.soilColor || {
      top: "#262c1c",
      front: "#1c2014",
      side: "#12160e"
    };

    // Front-left face
    ctx.beginPath();
    ctx.moveTo(t3.x, t3.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(b2.x, b2.y);
    ctx.lineTo(b3.x, b3.y);
    ctx.closePath();
    ctx.fillStyle = soil.front;
    ctx.fill();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Root-zone moisture W band along profile
    const moistureFrac = Math.min(1.0, this.state.W / 180);
    const mwHeight = sh * moistureFrac * 0.7;
    const mwTop = this.isoProject(0, sl, botZ + mwHeight, ox, oy);
    const mwRight = this.isoProject(sw, sl, botZ + mwHeight, ox, oy);

    ctx.beginPath();
    ctx.moveTo(mwTop.x, mwTop.y);
    ctx.lineTo(mwRight.x, mwRight.y);
    ctx.lineTo(b2.x, b2.y);
    ctx.lineTo(b3.x, b3.y);
    ctx.closePath();
    ctx.fillStyle = "rgba(56, 189, 248, 0.22)"; // Root-zone moisture blue
    ctx.fill();

    // Front-right face
    ctx.beginPath();
    ctx.moveTo(t1.x, t1.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(b2.x, b2.y);
    ctx.lineTo(b1.x, b1.y);
    ctx.closePath();
    ctx.fillStyle = soil.side;
    ctx.fill();
    ctx.stroke();

    // Top surface (arable topsoil)
    ctx.beginPath();
    ctx.moveTo(t0.x, t0.y);
    ctx.lineTo(t1.x, t1.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(t3.x, t3.y);
    ctx.closePath();
    ctx.fillStyle = soil.top;
    ctx.fill();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // If topsoil has subsided due to erosion, draw runoff scars / rocky cracks
    if (sinkingZ > 6) {
      ctx.strokeStyle = "rgba(100, 116, 139, 0.4)";
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      const r1 = this.isoProject(sw * 0.2, sl * 0.3, topZ, ox, oy);
      const r2 = this.isoProject(sw * 0.7, sl * 0.8, topZ, ox, oy);
      ctx.moveTo(r1.x, r1.y);
      ctx.lineTo(r2.x, r2.y);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  /**
   * 2. Square hills and terraces (stepped agricultural benches as in the sketch)
   */
  drawSquareTerraces(ctx, ox, oy, sh, sinkingZ) {
    const topZ = -sinkingZ;

    // Terrace 1 (Elevated along the hillside)
    const tx = 55;
    const ty = 30;
    const tw = 75;
    const tl = 55;
    const th = 10;

    const t0 = this.isoProject(tx, ty, topZ + th, ox, oy);
    const t1 = this.isoProject(tx + tw, ty, topZ + th, ox, oy);
    const t2 = this.isoProject(tx + tw, ty + tl, topZ + th, ox, oy);
    const t3 = this.isoProject(tx, ty + tl, topZ + th, ox, oy);

    ctx.beginPath();
    ctx.moveTo(t0.x, t0.y);
    ctx.lineTo(t1.x, t1.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(t3.x, t3.y);
    ctx.closePath();
    ctx.fillStyle = "rgba(255, 255, 255, 0.05)";
    ctx.fill();
    ctx.strokeStyle = "rgba(56, 189, 248, 0.45)";
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.2;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  /**
   * 3. Agricultural crops (Green biomass B)
   */
  drawCrops(ctx, ox, oy, sh, sw, sl, sinkingZ) {
    const topZ = -sinkingZ;
    const rows = 4;
    const cols = 5;
    const growthScale = Math.min(1.4, Math.max(0.4, (this.state.B || 10) / 12));

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const cx = 25 + (c * (sw - 50) / (cols - 1));
        const cy = 20 + (r * (sl - 40) / (rows - 1));
        const isTerrace = (cx >= 55 && cx <= 130 && cy >= 30 && cy <= 85);
        const z = topZ + (isTerrace ? 10 : 0);

        const pos = this.isoProject(cx, cy, z, ox, oy);

        ctx.save();
        ctx.translate(pos.x, pos.y);

        // Stem
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(0, -11 * growthScale);
        ctx.strokeStyle = this.state.Psi < 0.38 ? "#eab308" : "#10b981"; // Yellow under critical stress
        ctx.lineWidth = 1.4;
        ctx.stroke();

        // Leaves
        ctx.beginPath();
        ctx.arc(-3.5 * growthScale, -9 * growthScale, 3 * growthScale, 0, Math.PI * 2);
        ctx.arc(3.5 * growthScale, -10 * growthScale, 3 * growthScale, 0, Math.PI * 2);
        ctx.fillStyle = this.state.Psi < 0.38 ? "#ca8a04" : "#34d399";
        ctx.fill();

        ctx.restore();
      }
    }
  }

  /**
   * 3.1 Stubble / transition soil (Bare soil with dry residues)
   */
  drawStubbleResidue(ctx, ox, oy, sh, sw, sl, sinkingZ) {
    const topZ = -sinkingZ;
    ctx.strokeStyle = "rgba(217, 119, 6, 0.4)";
    ctx.lineWidth = 1.2;

    for (let i = 0; i < 20; i++) {
      const rx = 20 + (i * 73) % (sw - 40);
      const ry = 15 + (i * 47) % (sl - 30);
      const p = this.isoProject(rx, ry, topZ, ox, oy);

      ctx.beginPath();
      ctx.moveTo(p.x - 3, p.y + 2);
      ctx.lineTo(p.x + 3, p.y - 2);
      ctx.stroke();
    }
  }

  /**
   * 4. Anchor pillars (dashed lines)
   */
  drawShieldPilars(ctx, ox, oy, sw, sl, sz, sinkingZ) {
    const topZ = -sinkingZ;
    const corners = [
      { x: 0, y: 0 },
      { x: sw, y: 0 },
      { x: sw, y: sl },
      { x: 0, y: sl }
    ];

    const isOff = this.state.shieldState === "desactivado";
    ctx.strokeStyle = isOff ? "rgba(100, 116, 139, 0.2)" : this.state.shieldColor;
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 4]);

    corners.forEach(c => {
      const bot = this.isoProject(c.x, c.y, topZ, ox, oy);
      const top = this.isoProject(c.x, c.y, sz, ox, oy);

      ctx.beginPath();
      ctx.moveTo(bot.x, bot.y);
      ctx.lineTo(top.x, top.y);
      ctx.stroke();

      // Anchor node
      ctx.beginPath();
      ctx.arc(bot.x, bot.y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fill();
    });

    ctx.setLineDash([]);
  }

  /**
   * 5. SUSPENDED FLAT SHIELD WITH 4 STATES
   */
  drawFlatShield(ctx, ox, oy, sw, sl, sz) {
    const state = this.state.shieldState; // "azul_cobalto" | "violeta_ambar" | "rojo_intenso" | "desactivado"

    // Protection plane vertices
    const g0 = this.isoProject(0, 0, sz, ox, oy);
    const g1 = this.isoProject(sw, 0, sz, ox, oy);
    const g2 = this.isoProject(sw, sl, sz, ox, oy);
    const g3 = this.isoProject(0, sl, sz, ox, oy);

    // =========================================================================
    // STATE 4: SHIELD DEACTIVATED (q = Transition / Bare Soil)
    // =========================================================================
    if (state === "desactivado") {
      ctx.beginPath();
      ctx.moveTo(g0.x, g0.y);
      ctx.lineTo(g1.x, g1.y);
      ctx.lineTo(g2.x, g2.y);
      ctx.lineTo(g3.x, g3.y);
      ctx.closePath();
      ctx.strokeStyle = "rgba(100, 116, 139, 0.35)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
      return;
    }

    // Configuration per active state:
    // 1. Cobalt Blue (Psi -> 1): #2563eb / #1d4ed8
    // 2. Violet / Amber (Psi ~ 0.5): #8b5cf6 / #d97706
    // 3. Deep Red (Psi -> 0): #dc2626 / #ef4444
    let baseColor = "#2563eb";
    let glowRgba = "rgba(37, 99, 235, 0.28)";
    let pulseSpeed = 1.0;

    if (state === "azul_cobalto") {
      baseColor = "#2563eb"; // Cobalt Blue
      glowRgba = "rgba(37, 99, 235, 0.35)";
      pulseSpeed = 1.0;
    } else if (state === "violeta_ambar") {
      baseColor = "#8b5cf6"; // Violet with amber highlights
      glowRgba = "rgba(139, 92, 246, 0.32)";
      pulseSpeed = 1.8;
    } else if (state === "rojo_intenso") {
      baseColor = "#dc2626"; // Critical Deep Red
      glowRgba = "rgba(220, 38, 38, 0.45)";
      pulseSpeed = 3.5; // Fast alarm pulse
    }

    // Shield breathing pulse
    const pulseFactor = Math.sin(this.animTime * pulseSpeed * 2);
    const alphaPulse = Math.max(0.15, Math.min(0.65, 0.30 + pulseFactor * 0.15));

    // Translucent plane
    ctx.beginPath();
    ctx.moveTo(g0.x, g0.y);
    ctx.lineTo(g1.x, g1.y);
    ctx.lineTo(g2.x, g2.y);
    ctx.lineTo(g3.x, g3.y);
    ctx.closePath();
    ctx.fillStyle = glowRgba.replace(/[\d\.]+\)$/, `${alphaPulse})`);
    ctx.fill();

    // Flat shield wireframe grid
    const cols = 5;
    const rows = 4;
    ctx.strokeStyle = baseColor;
    ctx.lineWidth = 1.4;

    for (let c = 0; c <= cols; c++) {
      const gx = c * (sw / cols);
      const pS = this.isoProject(gx, 0, sz, ox, oy);
      const pE = this.isoProject(gx, sl, sz, ox, oy);
      ctx.beginPath();
      ctx.moveTo(pS.x, pS.y);
      ctx.lineTo(pE.x, pE.y);
      ctx.stroke();
    }

    for (let r = 0; r <= rows; r++) {
      const gy = r * (sl / rows);
      const pS = this.isoProject(0, gy, sz, ox, oy);
      const pE = this.isoProject(sw, gy, sz, ox, oy);
      ctx.beginPath();
      ctx.moveTo(pS.x, pS.y);
      ctx.lineTo(pE.x, pE.y);
      ctx.stroke();
    }
  }

  /**
   * 6. Top HUD with State and Psi indicator
   */
  drawHUD(ctx, ox, oy, sw, sl, sz) {
    const centerTop = this.isoProject(sw / 2, sl / 2, sz + 18, ox, oy, false);

    ctx.save();
    const badgeW = 210;
    const badgeH = 28;
    const bx = centerTop.x - badgeW / 2;
    const by = centerTop.y - 15;

    ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
    ctx.strokeStyle = this.state.shieldColor;
    ctx.lineWidth = 1.5;

    ctx.beginPath();
    ctx.roundRect(bx, by, badgeW, badgeH, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";

    const psiPct = Math.round((this.state.Psi || 0) * 100);
    let stateLabel = "";

    switch (this.state.shieldState) {
      case "azul_cobalto":
        stateLabel = `🔵 Cobalt Blue (Ψ=${this.state.Psi})`;
        break;
      case "violeta_ambar":
        stateLabel = `🟣 Violet/Amber (Ψ=${this.state.Psi})`;
        break;
      case "rojo_intenso":
        stateLabel = `🔴 Deep Red (Ψ=${this.state.Psi})`;
        break;
      default:
        stateLabel = `⚪ Shield Deactivated (Transition)`;
    }

    ctx.fillText(`${stateLabel}`, centerTop.x, by + 18);
    ctx.restore();
  }

  startAnimationLoop() {
    const loop = () => {
      this.render();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }
}
