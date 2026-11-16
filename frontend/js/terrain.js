import { parcelFootprint } from './parcel-geometry.js';

export const decodeTerrarium = (r, g, b) => r * 256 + g + b / 256 - 32768;
export const metersPerWorldPixel = y => 156543.03392804097 / Math.cosh(Math.PI * (1 - 2 * y / 256));
// Purely visual enhancement, bounded to preserve viewport framing.
export const exaggerateRelief = height => 55 * Math.tanh(height * 4 / 55);
export function reliefColor(level, erosion = 0) {
  const amount = Math.min(1, Math.abs(level));
  const base = [64, 170, 145];
  const target = level >= 0 ? [255, 190, 55] : [143, 105, 255];
  const red = Math.min(0.85, Math.max(0, erosion));
  const rgb = base.map((value, i) => Math.round((value + (target[i] - value) * amount) * (1 - red)
    + [245, 65, 55][i] * red));
  return `rgb(${rgb.join(',')})`;
}

// Cache shared between map and viewer. Never replace a missing DEM with invented mountains.
export class TerrainSurface {
  constructor() {
    this.tiles = new Map();
    this.pending = new Map();
    this.failures = new Map();
    this.controls = { slopeTheta: 8 };
    this.physics = {};
  }

  setParcel(geometry) {
    this.footprint = parcelFootprint(geometry);
  }

  async loadTile(z, x, y) {
    const count = 2 ** z;
    if (y < 0 || y >= count) return;
    x = ((x % count) + count) % count;
    const key = `${z}/${x}/${y}`;
    if (this.tiles.has(key)) return;
    if (this.pending.has(key)) return this.pending.get(key);
    if (Date.now() - (this.failures.get(key) || 0) < 30000) throw new Error('DEM unavailable');
    const promise = new Promise((resolve, reject) => {
      const image = new Image();
      image.crossOrigin = 'anonymous';
      const timer = setTimeout(() => { image.src = ''; reject(new Error('DEM timeout')); }, 12000);
      image.onerror = () => { clearTimeout(timer); reject(new Error('Failed to load DEM')); };
      image.onload = () => {
        clearTimeout(timer);
        try {
          const canvas = document.createElement('canvas');
          canvas.width = canvas.height = 256;
          const ctx = canvas.getContext('2d', { willReadFrequently: true });
          ctx.drawImage(image, 0, 0, 256, 256);
          const rgba = ctx.getImageData(0, 0, 256, 256).data;
          const heights = new Float32Array(256 * 256);
          for (let i = 0; i < heights.length; i++) heights[i] = decodeTerrarium(...rgba.subarray(i * 4, i * 4 + 3));
          this.tiles.set(key, heights);
          // Keep cache memory bounded while exploring the map.
          while (this.tiles.size > 128) this.tiles.delete(this.tiles.keys().next().value);
          resolve();
        } catch (error) { reject(error); }
      };
      image.src = `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/${key}.png`;
    });
    this.pending.set(key, promise);
    try { await promise; } catch (error) { this.failures.set(key, Date.now()); throw error; }
    finally { this.pending.delete(key); }
  }

  async loadBounds(minX, minY, maxX, maxY, zoom = 14) {
    let z = Math.max(0, Math.min(14, Math.floor(zoom)));
    let factor = 2 ** z / 256;
    while (z > 0 && (Math.floor(maxX * factor) - Math.floor(minX * factor) + 1)
      * (Math.floor(maxY * factor) - Math.floor(minY * factor) + 1) > 16) {
      factor = 2 ** --z / 256;
    }
    const jobs = [];
    for (let x = Math.floor(minX * factor); x <= Math.floor(maxX * factor); x++) {
      for (let y = Math.floor(minY * factor); y <= Math.floor(maxY * factor); y++) jobs.push(this.loadTile(z, x, y));
    }
    const results = await Promise.allSettled(jobs);
    return results.every(r => r.status === 'fulfilled');
  }

  sample(x, y, zoom = 14) {
    for (let z = Math.min(14, Math.floor(zoom)); z >= 0; z--) {
      // DEM values are located at pixel centers. Interpolate across tile borders.
      const px = x * 2 ** z - 0.5, py = y * 2 ** z - 0.5;
      const ix = Math.floor(px), iy = Math.floor(py), fx = px - ix, fy = py - iy;
      const pixel = (a, b) => {
        const count = 2 ** z;
        const tx = ((Math.floor(a / 256) % count) + count) % count, ty = Math.floor(b / 256);
        const tile = this.tiles.get(`${z}/${tx}/${ty}`);
        return tile ? tile[((b % 256 + 256) % 256) * 256 + ((a % 256 + 256) % 256)] : null;
      };
      const values = [pixel(ix, iy), pixel(ix + 1, iy), pixel(ix, iy + 1), pixel(ix + 1, iy + 1)];
      if (values.every(v => v !== null)) return (values[0] * (1 - fx) + values[1] * fx) * (1 - fy)
        + (values[2] * (1 - fx) + values[3] * fx) * fy;
    }
    return null;
  }

  contains(x, y) {
    const f = this.footprint;
    if (!f) return false;
    const px = f.offsetX + (x - f.minX) * f.scale, py = f.offsetY + (y - f.minY) * f.scale;
    return f.polygons.some(polygon => {
      let inside = false;
      for (const ring of polygon) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [ax, ay] = ring[i], [bx, by] = ring[j];
        if ((ay > py) !== (by > py) && px < (bx - ax) * (py - ay) / (by - ay) + ax) inside = !inside;
      }
      return inside;
    });
  }

  perturbation(x, y) {
    const f = this.footprint;
    if (!f) return 0;
    const u = (x - f.minX) / f.width, v = (y - f.minY) / f.height;
    const distance = (v - 0.5) * f.height * metersPerWorldPixel(y);
    const slope = Math.tan((this.controls.slopeTheta ?? 8) * Math.PI / 180) - Math.tan(8 * Math.PI / 180);
    // Erosion amplified 250x to make millimeter losses visible.
    const erosion = (this.physics.erosionSinkingMm || 0) / 1000 * 250;
    return distance * slope - erosion * (0.4 + 0.6 * Math.sin(Math.PI * u) ** 2 * Math.sin(Math.PI * v) ** 2);
  }

  height(x, y, zoom = 14, parcel = false) {
    const elevation = this.sample(x, y, zoom);
    if (elevation === null) return null;
    return elevation + ((parcel || this.contains(x, y)) ? this.perturbation(x, y) : 0);
  }

  visualColor(x, y, localLevel = 0, zoom = 14, parcel = false) {
    const f = this.footprint;
    if (!f || (!parcel && !this.contains(x, y))) return reliefColor(localLevel);
    const centerY = f.minY + f.height / 2;
    const reference = this.sample(f.minX + f.width / 2, centerY, zoom);
    const height = this.height(x, y, zoom, true);
    if (reference === null || height === null) return reliefColor(0);
    const level = exaggerateRelief((height - reference) * f.scale / metersPerWorldPixel(centerY)) / 35;
    const u = (x - f.minX) / f.width, v = (y - f.minY) / f.height;
    const erosion = Math.min(0.85, (this.physics.erosionSinkingMm || 0) / 18)
      * Math.sin(Math.PI * u) ** 2 * Math.sin(Math.PI * v) ** 2;
    return reliefColor(level, erosion);
  }
}
