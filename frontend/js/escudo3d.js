/**
 * AgroPhasor - Visor Isométrico 2.5D "Cerros en Cuadrado + Escudo Plano + Curvas"
 * Sincronizado en tiempo real con el modelo físico:
 * - Hundimiento físico de la tierra por erosión (H)
 * - Transición de color del suelo: Marrón fértil <-> Gris rocoso degradado
 * - Altura del dosel según biomasa aérea (B)
 * - Malla de Lissajous que respira y modula su área de protección
 * - 4 Estados del Escudo:
 *     1. Azul Cobalto (Psi -> 1)
 *     2. Violeta / Ámbar (Psi ~ 0.5)
 *     3. Rojo Intenso (Psi -> 0)
 *     4. Escudo Desactivado (q = Transición, suelo desnudo)
 */

export class Escudo3DViewer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    // Estado físico sincronizado
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
      limitingNutrient: "Nitrógeno (N)",
      Psi: 0.85,
      shieldState: "azul_cobalto", // "azul_cobalto" | "violeta_ambar" | "rojo_intenso" | "desactivado"
      shieldColor: "#2563eb",
      shieldName: "Azul Cobalto (Óptima Resiliencia)",
      stage: "cultivo",
      cropName: "Papa Canchán"
    };

    // Parámetros de proyección isométrica
    this.angle = Math.PI / 6; // 30 grados
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
   * Actualizar el estado completo desde el motor de física
   */
  updatePhysicsState(physData) {
    if (!physData) return;
    Object.assign(this.state, physData);
  }

  // Transformación isométrica 3D -> 2D con rotación interactiva
  isoProject(x, y, z, originX, originY) {
    // Centro del bloque
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

    // Dimensiones del bloque cuadrado de tierra
    const slabW = 190;
    const slabL = 130;
    
    // 1. HUNDIMIENTO DE LA TIERRA POR EROSIÓN
    // A mayor erosión (erosionSinkingMm), el sustrato se hunde en el eje Z
    const visualSinkingZ = Math.min(22, (this.state.erosionSinkingMm || 0) * 0.5);
    const baseHeight = 26; // Espesor visual
    const effectiveSlabH = Math.max(8, baseHeight - visualSinkingZ);

    // 2. ALTURA DEL ESCUDO PLANO
    // Depende de la biomasa B (dosel vegetal). En transición baja cerca al suelo
    let shieldHeight = 75;
    if (this.state.stage === "transicion") {
      shieldHeight = 35; // Colapsado en barbecho/suelo desnudo
    } else {
      const biomassOffset = Math.min(25, (this.state.B || 10) * 1.5);
      shieldHeight = 55 + biomassOffset + Math.sin(this.animTime * 1.5) * 2;
    }

    // 1. DIBUJAR LOSA DE SUELO CUADRADA CON COLOR DEGRADADO Y HUNDIMIENTO
    this.drawSquareSlab(ctx, originX, originY, slabW, slabL, effectiveSlabH, visualSinkingZ);

    // 2. DIBUJAR CERROS Y ANDENES EN CUADRADO (Terrazas agrícolas andinas)
    this.drawSquareTerraces(ctx, originX, originY, effectiveSlabH, visualSinkingZ);

    // 3. DIBUJAR CULTIVOS (Solo si no está en transición)
    if (this.state.stage !== "transicion") {
      this.drawCrops(ctx, originX, originY, effectiveSlabH, slabW, slabL, visualSinkingZ);
    } else {
      this.drawStubbleResidue(ctx, originX, originY, effectiveSlabH, slabW, slabL, visualSinkingZ);
    }

    // 4. PILARES DE CONEXIÓN ENTRE SUELO Y ESCUDO
    this.drawShieldPilars(ctx, originX, originY, slabW, slabL, shieldHeight, visualSinkingZ);

    // 5. ESCUDO PLANO SUSPENDIDO CON ÁREA DE LISSAJOUS Y LOS 4 ESTADOS
    this.drawFlatShield(ctx, originX, originY, slabW, slabL, shieldHeight);

    // 6. HUD Y ETIQUETA EN VIVO DEL ESCUDO
    this.drawHUD(ctx, originX, originY, slabW, slabL, shieldHeight);
  }

  /**
   * 1. Losa cuadrada de tierra: Marrón fértil <-> Gris rocoso y hundimiento
   */
  drawSquareSlab(ctx, ox, oy, sw, sl, sh, sinkingZ) {
    const topZ = -sinkingZ;
    const botZ = -sinkingZ - sh;

    // Vértices inferiores
    const b0 = this.isoProject(0, 0, botZ, ox, oy);
    const b1 = this.isoProject(sw, 0, botZ, ox, oy);
    const b2 = this.isoProject(sw, sl, botZ, ox, oy);
    const b3 = this.isoProject(0, sl, botZ, ox, oy);

    // Vértices superiores (con hundimiento)
    const t0 = this.isoProject(0, 0, topZ, ox, oy);
    const t1 = this.isoProject(sw, 0, topZ, ox, oy);
    const t2 = this.isoProject(sw, sl, topZ, ox, oy);
    const t3 = this.isoProject(0, sl, topZ, ox, oy);

    const soil = this.state.soilColor || {
      top: "#262c1c",
      front: "#1c2014",
      side: "#12160e"
    };

    // Cara frontal izquierda
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

    // Franja de humedad radicular W en el perfil
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
    ctx.fillStyle = "rgba(56, 189, 248, 0.22)"; // Azul humedad radicular
    ctx.fill();

    // Cara frontal derecha
    ctx.beginPath();
    ctx.moveTo(t1.x, t1.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(b2.x, b2.y);
    ctx.lineTo(b1.x, b1.y);
    ctx.closePath();
    ctx.fillStyle = soil.side;
    ctx.fill();
    ctx.stroke();

    // Superficie Superior (Suelo cultivable)
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

    // Si el suelo se ha hundido por erosión, dibujar marcas de escorrentía/grietas rocosas
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
   * 2. Cerros y andenes en cuadrado (Terrazas escalonadas como en el boceto)
   */
  drawSquareTerraces(ctx, ox, oy, sh, sinkingZ) {
    const topZ = -sinkingZ;

    // Terraza 1 (Elevada en la ladera)
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
   * 3. Cultivos agrícolas (Biomasa B verde)
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

        // Tallo
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(0, -11 * growthScale);
        ctx.strokeStyle = this.state.Psi < 0.38 ? "#eab308" : "#10b981"; // Amarillo si estrés crítico
        ctx.lineWidth = 1.4;
        ctx.stroke();

        // Hojas
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
   * 3.1 Rastrojo / suelo en transición (Suelo desnudo con restos secos)
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
   * 4. Pilares de anclaje (con líneas discontinuas)
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

      // Nodo de anclaje
      ctx.beginPath();
      ctx.arc(bot.x, bot.y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fill();
    });

    ctx.setLineDash([]);
  }

  /**
   * 5. ESCUDO PLANO SUSPENDIDO CON ÁREA DE LISSAJOUS Y 4 ESTADOS
   */
  drawFlatShield(ctx, ox, oy, sw, sl, sz) {
    const state = this.state.shieldState; // "azul_cobalto" | "violeta_ambar" | "rojo_intenso" | "desactivado"

    // Vértices del plano de protección
    const g0 = this.isoProject(0, 0, sz, ox, oy);
    const g1 = this.isoProject(sw, 0, sz, ox, oy);
    const g2 = this.isoProject(sw, sl, sz, ox, oy);
    const g3 = this.isoProject(0, sl, sz, ox, oy);

    // =========================================================================
    // ESTADO 4: ESCUDO DESACTIVADO (q = Transición / Suelo Desnudo)
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

    // Configuración según el estado activo:
    // 1. Azul Cobalto (Psi -> 1): #2563eb / #1d4ed8
    // 2. Violeta / Ámbar (Psi ~ 0.5): #8b5cf6 / #d97706
    // 3. Rojo Intenso (Psi -> 0): #dc2626 / #ef4444
    let baseColor = "#2563eb";
    let glowRgba = "rgba(37, 99, 235, 0.28)";
    let pulseSpeed = 1.0;
    let lissajousScale = 1.0;

    if (state === "azul_cobalto") {
      baseColor = "#2563eb"; // Azul Cobalto
      glowRgba = "rgba(37, 99, 235, 0.35)";
      pulseSpeed = 1.0;
      lissajousScale = 1.0; // Área plena
    } else if (state === "violeta_ambar") {
      baseColor = "#8b5cf6"; // Violeta con destellos ámbar
      glowRgba = "rgba(139, 92, 246, 0.32)";
      pulseSpeed = 1.8;
      lissajousScale = 0.78; // Área contraída
    } else if (state === "rojo_intenso") {
      baseColor = "#dc2626"; // Rojo Intenso crítico
      glowRgba = "rgba(220, 38, 38, 0.45)";
      pulseSpeed = 3.5; // Parpadeo rápido de alarma
      lissajousScale = 0.55; // Escudo severamente reducido
    }

    // Pulsación de respiración del escudo
    const pulseFactor = Math.sin(this.animTime * pulseSpeed * 2);
    const alphaPulse = Math.max(0.15, Math.min(0.65, 0.30 + pulseFactor * 0.15));

    // Plano translúcido
    ctx.beginPath();
    ctx.moveTo(g0.x, g0.y);
    ctx.lineTo(g1.x, g1.y);
    ctx.lineTo(g2.x, g2.y);
    ctx.lineTo(g3.x, g3.y);
    ctx.closePath();
    ctx.fillStyle = glowRgba.replace(/[\d\.]+\)$/, `${alphaPulse})`);
    ctx.fill();

    // Malla cuadriculada del escudo plano
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

    // =========================================================================
    // ÁREA DE LISSAJOUS DE RESPIRACIÓN Y PROTECCIÓN
    // x(t) = A sin(3t), y(t) = B sin(2t + delta)
    // =========================================================================
    ctx.save();
    ctx.beginPath();
    const lissSteps = 60;
    const lissW = (sw * 0.45) * lissajousScale;
    const lissL = (sl * 0.45) * lissajousScale;
    const cx = sw / 2;
    const cy = sl / 2;

    for (let i = 0; i <= lissSteps; i++) {
      const theta = (i / lissSteps) * Math.PI * 2;
      const lx = cx + lissW * Math.sin(3 * theta + this.animTime * pulseSpeed);
      const ly = cy + lissL * Math.sin(2 * theta);
      const lp = this.isoProject(lx, ly, sz + 2, ox, oy);

      if (i === 0) ctx.moveTo(lp.x, lp.y);
      else ctx.lineTo(lp.x, lp.y);
    }

    ctx.closePath();
    ctx.strokeStyle = state === "violeta_ambar" ? "#f59e0b" : "#ffffff";
    ctx.lineWidth = 2.0;
    ctx.shadowColor = baseColor;
    ctx.shadowBlur = 12;
    ctx.stroke();
    ctx.restore();
  }

  /**
   * 6. HUD superior con indicador de Estado y Psi
   */
  drawHUD(ctx, ox, oy, sw, sl, sz) {
    const centerTop = this.isoProject(sw / 2, sl / 2, sz + 18, ox, oy);

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
        stateLabel = `🔵 Azul Cobalto (Ψ=${this.state.Psi})`;
        break;
      case "violeta_ambar":
        stateLabel = `🟣 Violeta/Ámbar (Ψ=${this.state.Psi})`;
        break;
      case "rojo_intenso":
        stateLabel = `🔴 Rojo Intenso (Ψ=${this.state.Psi})`;
        break;
      default:
        stateLabel = `⚪ Escudo Desactivado (Transición)`;
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
