/**
 * AgroPhasor - Visor Isométrico 2.5D "Escudo Ambiental y Gemelo Digital"
 * Renderiza el bloque de suelo (H, W), cultivos (B) y la malla suspendida del escudo protector (T)
 * Basado en el boceto conceptual del gemelo digital.
 */

export class Escudo3DViewer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    // Estado del modelo físico
    this.state = {
      humedad_W: 142.5,
      temperatura_T: 16.8,
      espesor_H: 278,
      escudoScore: 87,
      biomasa_B: 11.8,
      cropName: "Papa Canchán",
      cropIcon: "🥔",
      hasSubzone: true,
      shieldActive: true,
      shieldColor: "#38bdf8",
      glowColor: "rgba(56, 189, 248, 0.4)"
    };

    // Parámetros de renderizado isométrico
    this.angle = Math.PI / 6; // 30 grados
    this.scale = 1.0;
    this.rotation = 0; // Rotación interactiva leve
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
      this.width = rect.width || 380;
      this.height = rect.height || 260;
      this.canvas.width = this.width * dpr;
      this.canvas.height = this.height * dpr;
      this.ctx.scale(dpr, dpr);
      this.scale = Math.min(this.width / 340, this.height / 240);
    };

    resize();
    window.addEventListener('resize', resize);
  }

  bindInteractions() {
    if (!this.canvas) return;

    // Permitir rotación interactiva con el dedo o ratón
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

  updateMetrics(metrics) {
    if (!metrics) return;
    if (metrics.humedad_W !== undefined) this.state.humedad_W = metrics.humedad_W;
    if (metrics.temperatura_T !== undefined) this.state.temperatura_T = metrics.temperatura_T;
    if (metrics.espesor_H !== undefined) this.state.espesor_H = metrics.espesor_H;
    if (metrics.escudoScore !== undefined) this.state.escudoScore = metrics.escudoScore;
    if (metrics.biomasa_B !== undefined) this.state.biomasa_B = metrics.biomasa_B;
    if (metrics.cropName) this.state.cropName = metrics.cropName;
    if (metrics.cropIcon) this.state.cropIcon = metrics.cropIcon;

    // Color del escudo según resiliencia
    if (this.state.escudoScore >= 80) {
      this.state.shieldColor = "#10b981"; // Esmeralda óptimo
      this.state.glowColor = "rgba(16, 185, 129, 0.4)";
    } else if (this.state.escudoScore >= 50) {
      this.state.shieldColor = "#38bdf8"; // Azul medio
      this.state.glowColor = "rgba(56, 189, 248, 0.4)";
    } else {
      this.state.shieldColor = "#f59e0b"; // Ámbar estrés
      this.state.glowColor = "rgba(245, 158, 11, 0.4)";
    }
  }

  // Transformación isométrica de coordenadas 3D (x, y, z) a 2D (px, py)
  isoProject(x, y, z, originX, originY) {
    const effectiveAngle = this.angle + this.rotation;
    const cosA = Math.cos(effectiveAngle);
    const sinA = Math.sin(effectiveAngle);

    // Rotación suave respecto al centro del terreno
    const cx = x - 90;
    const cy = y - 60;
    const rx = cx * Math.cos(this.rotation) - cy * Math.sin(this.rotation);
    const ry = cx * Math.sin(this.rotation) + cy * Math.cos(this.rotation);

    const px = originX + (rx - ry) * Math.cos(this.angle) * this.scale;
    const py = originY + (rx + ry) * Math.sin(this.angle) * this.scale - (z * this.scale * 0.9);
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
    this.animTime += 0.03;

    // Dimensiones de la losa de terreno
    const slabW = 180;
    const slabL = 120;
    const slabH = 24; // Espesor fértil H
    const shieldZ = 70 + Math.sin(this.animTime * 1.5) * 3; // Flotación sutil del dosel

    // 1. DIBUJAR LOSA DE SUELO 3D (Espesor fértil H y Capa radicular W)
    this.drawSoilSlab(ctx, originX, originY, slabW, slabL, slabH);

    // 2. DIBUJAR SUB-ZONA / TERRAZA AGRÍCOLA (como en el boceto)
    if (this.state.hasSubzone) {
      this.drawSubzone(ctx, originX, originY, slabH);
    }

    // 3. DIBUJAR CULTIVOS AGRÍCOLAS (Biomasa verde B)
    this.drawCrops(ctx, originX, originY, slabH, slabW, slabL);

    // 4. DIBUJAR PILARES / VECTORES DE PROTECCIÓN (Líneas verticales que conectan el suelo al escudo)
    this.drawShieldPilars(ctx, originX, originY, slabW, slabL, slabH, shieldZ);

    // 5. DIBUJAR LA MALLA DEL ESCUDO AMBIENTAL (Canopy Grid suspendido en 3D)
    this.drawShieldGrid(ctx, originX, originY, slabW, slabL, shieldZ);

    // 6. AURA / ENTORNO CIRCUNDANTE (Aura verde como el dibujo)
    this.drawProtectiveAura(ctx, originX, originY, slabW, slabL, shieldZ);

    // 7. HUD Y ETIQUETAS FLOTANTES DE ESTADO
    this.drawHUD(ctx, originX, originY, slabW, slabL, shieldZ);
  }

  drawSoilSlab(ctx, ox, oy, sw, sl, sh) {
    // Vértices de la base inferior (z = -sh)
    const p0_b = this.isoProject(0, 0, -sh, ox, oy);
    const p1_b = this.isoProject(sw, 0, -sh, ox, oy);
    const p2_b = this.isoProject(sw, sl, -sh, ox, oy);
    const p3_b = this.isoProject(0, sl, -sh, ox, oy);

    // Vértices de la superficie superior (z = 0)
    const p0 = this.isoProject(0, 0, 0, ox, oy);
    const p1 = this.isoProject(sw, 0, 0, ox, oy);
    const p2 = this.isoProject(sw, sl, 0, ox, oy);
    const p3 = this.isoProject(0, sl, 0, ox, oy);

    // Cara frontal izquierda (z: -sh -> 0)
    ctx.beginPath();
    ctx.moveTo(p3.x, p3.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p2_b.x, p2_b.y);
    ctx.lineTo(p3_b.x, p3_b.y);
    ctx.closePath();
    ctx.fillStyle = "#1e293b";
    ctx.fill();
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Franja de humedad radicular W en la cara frontal
    const moistureH = Math.min(sh * (this.state.humedad_W / 180), sh);
    const pw_top = this.isoProject(0, sl, -sh + moistureH, ox, oy);
    const pw_right = this.isoProject(sw, sl, -sh + moistureH, ox, oy);
    ctx.beginPath();
    ctx.moveTo(pw_top.x, pw_top.y);
    ctx.lineTo(pw_right.x, pw_right.y);
    ctx.lineTo(p2_b.x, p2_b.y);
    ctx.lineTo(p3_b.x, p3_b.y);
    ctx.closePath();
    ctx.fillStyle = "rgba(56, 189, 248, 0.18)"; // Azul humedad radicular
    ctx.fill();

    // Cara frontal derecha
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p2_b.x, p2_b.y);
    ctx.lineTo(p1_b.x, p1_b.y);
    ctx.closePath();
    ctx.fillStyle = "#0f172a";
    ctx.fill();
    ctx.strokeStyle = "#334155";
    ctx.stroke();

    // Superficie Superior (Suelo cultivable)
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p3.x, p3.y);
    ctx.closePath();
    
    // Gradiente de fertilidad de suelo
    const grad = ctx.createLinearGradient(p0.x, p0.y, p2.x, p2.y);
    grad.addColorStop(0, "#142d1f"); // Tierra fértil profunda
    grad.addColorStop(1, "#0d1f15");
    ctx.fillStyle = grad;
    ctx.fill();
    ctx.strokeStyle = "rgba(16, 185, 129, 0.5)";
    ctx.lineWidth = 1.8;
    ctx.stroke();
  }

  drawSubzone(ctx, ox, oy, sh) {
    // Sub-zona interna (Mesa/Terraza central del boceto)
    const zx = 60;
    const zy = 35;
    const zw = 70;
    const zl = 50;
    const zh = 8; // Elevación de terraza

    const s0 = this.isoProject(zx, zy, zh, ox, oy);
    const s1 = this.isoProject(zx + zw, zy, zh, ox, oy);
    const s2 = this.isoProject(zx + zw, zy + zl, zh, ox, oy);
    const s3 = this.isoProject(zx, zy + zl, zh, ox, oy);

    // Contorno de la terraza
    ctx.beginPath();
    ctx.moveTo(s0.x, s0.y);
    ctx.lineTo(s1.x, s1.y);
    ctx.lineTo(s2.x, s2.y);
    ctx.lineTo(s3.x, s3.y);
    ctx.closePath();
    ctx.fillStyle = "rgba(16, 185, 129, 0.12)";
    ctx.fill();
    ctx.strokeStyle = "rgba(56, 189, 248, 0.7)";
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.2;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  drawCrops(ctx, ox, oy, sh, sw, sl) {
    // Matriz de plantas cultivadas
    const rows = 4;
    const cols = 5;
    const cropScale = Math.min(Math.max(this.state.biomasa_B / 10, 0.7), 1.4);

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const cx = 25 + (c * (sw - 50) / (cols - 1));
        const cy = 20 + (r * (sl - 40) / (rows - 1));
        const baseZ = (cx >= 60 && cx <= 130 && cy >= 35 && cy <= 85) ? 8 : 0;

        const pos = this.isoProject(cx, cy, baseZ, ox, oy);

        // Pequeño brote/planta verde
        ctx.save();
        ctx.translate(pos.x, pos.y);
        
        // Tallo
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(0, -12 * cropScale);
        ctx.strokeStyle = "#10b981";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Hojas
        ctx.beginPath();
        ctx.arc(-4 * cropScale, -10 * cropScale, 3.5 * cropScale, 0, Math.PI * 2);
        ctx.arc(4 * cropScale, -11 * cropScale, 3.5 * cropScale, 0, Math.PI * 2);
        ctx.fillStyle = "#34d399";
        ctx.fill();

        ctx.restore();
      }
    }
  }

  drawShieldPilars(ctx, ox, oy, sw, sl, sh, sz) {
    // Pilares en las 4 esquinas del terreno conectando al dosel
    const corners = [
      { x: 0, y: 0 },
      { x: sw, y: 0 },
      { x: sw, y: sl },
      { x: 0, y: sl }
    ];

    ctx.strokeStyle = this.state.shieldColor;
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 4]);

    corners.forEach(c => {
      const bottom = this.isoProject(c.x, c.y, 0, ox, oy);
      const top = this.isoProject(c.x, c.y, sz, ox, oy);

      ctx.beginPath();
      ctx.moveTo(bottom.x, bottom.y);
      ctx.lineTo(top.x, top.y);
      ctx.stroke();

      // Punto de anclaje luminoso
      ctx.beginPath();
      ctx.arc(bottom.x, bottom.y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = this.state.shieldColor;
      ctx.fill();
    });

    ctx.setLineDash([]);
  }

  drawShieldGrid(ctx, ox, oy, sw, sl, sz) {
    const gridCols = 5;
    const gridRows = 4;

    // Vértices del techo del escudo
    const g0 = this.isoProject(0, 0, sz, ox, oy);
    const g1 = this.isoProject(sw, 0, sz, ox, oy);
    const g2 = this.isoProject(sw, sl, sz, ox, oy);
    const g3 = this.isoProject(0, sl, sz, ox, oy);

    // Fondo translúcido del escudo protector
    ctx.beginPath();
    ctx.moveTo(g0.x, g0.y);
    ctx.lineTo(g1.x, g1.y);
    ctx.lineTo(g2.x, g2.y);
    ctx.lineTo(g3.x, g3.y);
    ctx.closePath();
    ctx.fillStyle = this.state.glowColor;
    ctx.fill();

    // Líneas longitudinales de la malla
    ctx.strokeStyle = this.state.shieldColor;
    ctx.lineWidth = 1.4;

    for (let c = 0; c <= gridCols; c++) {
      const gx = c * (sw / gridCols);
      const pStart = this.isoProject(gx, 0, sz, ox, oy);
      const pEnd = this.isoProject(gx, sl, sz, ox, oy);

      ctx.beginPath();
      ctx.moveTo(pStart.x, pStart.y);
      ctx.lineTo(pEnd.x, pEnd.y);
      ctx.stroke();
    }

    // Líneas transversales de la malla
    for (let r = 0; r <= gridRows; r++) {
      const gy = r * (sl / gridRows);
      const pStart = this.isoProject(0, gy, sz, ox, oy);
      const pEnd = this.isoProject(sw, gy, sz, ox, oy);

      ctx.beginPath();
      ctx.moveTo(pStart.x, pStart.y);
      ctx.lineTo(pEnd.x, pEnd.y);
      ctx.stroke();
    }

    // Onda de pulso de escaneo energético
    const pulseOffset = (this.animTime * 40) % sw;
    const pulseStart = this.isoProject(pulseOffset, 0, sz, ox, oy);
    const pulseEnd = this.isoProject(pulseOffset, sl, sz, ox, oy);
    ctx.beginPath();
    ctx.moveTo(pulseStart.x, pulseStart.y);
    ctx.lineTo(pulseEnd.x, pulseEnd.y);
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2.5;
    ctx.shadowColor = this.state.shieldColor;
    ctx.shadowBlur = 10;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  drawProtectiveAura(ctx, ox, oy, sw, sl, sz) {
    // El óvalo verde circundante como en el dibujo del usuario
    const auraCenter = this.isoProject(sw / 2, sl / 2, sz / 2, ox, oy);
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(auraCenter.x, auraCenter.y, 140 * this.scale, 75 * this.scale, 0, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(16, 185, 129, 0.4)";
    ctx.lineWidth = 1.8;
    ctx.setLineDash([8, 6]);
    ctx.stroke();
    ctx.restore();
  }

  drawHUD(ctx, ox, oy, sw, sl, sz) {
    const centerTop = this.isoProject(sw / 2, sl / 2, sz + 15, ox, oy);

    ctx.save();
    // Badge superior flotante
    ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
    ctx.strokeStyle = this.state.shieldColor;
    ctx.lineWidth = 1.2;

    const badgeW = 145;
    const badgeH = 26;
    const bx = centerTop.x - badgeW / 2;
    const by = centerTop.y - 15;

    ctx.beginPath();
    ctx.roundRect(bx, by, badgeW, badgeH, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(`🛡️ Escudo: ${this.state.escudoScore}% | ${this.state.temperatura_T}°C`, centerTop.x, by + 17);
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
