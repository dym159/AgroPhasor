import test from 'node:test';
import assert from 'node:assert/strict';
import { TerrainSurface, decodeTerrarium } from '../frontend/js/terrain.js';
import { Escudo3DViewer } from '../frontend/js/escudo3d.js';
import {
  buildParcelSimulationMesh,
  shieldColor,
  lissajousShieldScore,
  soilColorRgb,
} from '../frontend/src/services/parcelSimulationMesh.js';
import { applyTimelineSnapshot } from '../frontend/src/utils/phaseDates.js';

test('Terrarium decodes altitude, including fractional and negative elevations', () => {
  assert.equal(decodeTerrarium(137, 219, 68), 2523.265625);
  assert.equal(decodeTerrarium(128, 0, 0), 0);
  assert.equal(decodeTerrarium(127, 255, 128), -0.5);
});

test('DEM interpolation stays continuous across adjacent tiles; missing heights remain unknown', () => {
  const surface = new TerrainSurface();
  assert.equal(surface.sample(128, 128, 1), null);
  for (let tx = 0; tx < 2; tx++) for (let ty = 0; ty < 2; ty++) {
    const pixels = new Float32Array(256 * 256);
    for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) pixels[y * 256 + x] = tx * 256 + x;
    surface.tiles.set(`1/${tx}/${ty}`, pixels);
  }
  assert.equal(surface.sample(128, 128, 1), 255.5);
  assert(Math.abs(surface.sample(128.001, 128, 1) - surface.sample(127.999, 128, 1) - 0.004) < 1e-8);
});

const geometry = { type: 'Polygon', coordinates: [
  [[-75.21, -12.06], [-75.20, -12.06], [-75.20, -12.07], [-75.21, -12.07], [-75.21, -12.06]],
  [[-75.207, -12.063], [-75.203, -12.063], [-75.203, -12.067], [-75.207, -12.067], [-75.207, -12.063]]
] };

test('The active 3D view keeps cell geometry and applies cumulative soil loss to its elevation', () => {
  const parcel = { polygon: geometry.coordinates[0].map(([lon, lat]) => [lat, lon]) };
  const cell = {
    geometry, longitude: -75.209, latitude: -12.061, altitude_m: 3250,
    soil_color_rgb: [101, 67, 33], accumulated_erosion_mm: 0,
  };
  const eroded = { ...cell, soil_color_rgb: [128, 128, 128], accumulated_erosion_mm: 200 };
  const doubleLoss = { ...eroded, accumulated_erosion_mm: 400 };
  const { cells: [first, second, third] } = buildParcelSimulationMesh(parcel, [cell, eroded, doubleLoss]);
  assert.equal(first.polygons[0].length, 2);
  assert.equal(second.z - first.z, third.z - second.z);
  assert(second.z < first.z);
  assert.equal(second.color, 'rgb(128,128,128)');
  assert.equal(shieldColor(0), 'rgb(249,64,70)');
  assert.equal(shieldColor(0.5), 'rgb(146,110,163)');
  assert.equal(shieldColor(1), 'rgb(42,155,255)');
  // Lissajous area drives shield score (low area -> red, high area -> blue)
  assert(lissajousShieldScore(1.0, 0.2) < lissajousShieldScore(60.0, 0.9));
  // Precipitation variation lowers terrain height z
  const rainCell = { ...cell, rain_height_variation_mm: 25 };
  const { cells: [baseCell, rainyMeshCell] } = buildParcelSimulationMesh(parcel, [cell, rainCell]);
  assert(rainyMeshCell.z < baseCell.z);
  // Soil color transitions between brown [101,67,33] and gray [128,128,128] with nutrients & moisture
  assert.deepEqual(soilColorRgb({ retentionRatio: 1, etaNutrientes: 1, waterSaturation: 1 }), [101, 67, 33]);
  assert.deepEqual(soilColorRgb({ retentionRatio: 1, etaNutrientes: 0, waterSaturation: 0 }), [128, 128, 128]);
});

test('Slope and spatial erosion affect the shared surface only inside the parcel, preserving holes', () => {
  const surface = new TerrainSurface();
  surface.setParcel(geometry);
  surface.sample = () => 3250;
  const f = surface.footprint;
  const x = f.minX + f.width * 0.1, y = f.minY + f.height * 0.25;
  assert.equal(surface.height(x, y), 3250);
  surface.controls.slopeTheta = 25;
  surface.physics.erosionSinkingMm = 10;
  assert.notEqual(surface.height(x, y), 3250);
  assert.equal(surface.height(f.minX - f.width, y), 3250);
  assert.equal(surface.height(f.minX + f.width / 2, f.minY + f.height / 2), 3250);
  assert.notEqual(surface.perturbation(x, y), surface.perturbation(x, f.minY + f.height * 0.75));
});

test('3D terrain follows elevation while the upper shield stays planar', () => {
  const viewer = Object.create(Escudo3DViewer.prototype);
  const surface = new TerrainSurface();
  surface.setParcel(geometry);
  const f = surface.footprint;
  surface.sample = (x, y) => 3250 + (y - f.minY) / f.height * 25;
  Object.assign(viewer, { footprint: f, terrain: surface, rotation: 0, angle: Math.PI / 6, scale: 1 });
  const x = 50, y = 30;
  const offset = viewer.terrainOffset(x, y);
  assert.notEqual(offset, 0);
  const ground = viewer.isoProject(x, y, 0, 200, 200);
  const shield = viewer.isoProject(x, y, 70, 200, 200, false);
  const flatY = 200 + (x - 95 + y - 65) * Math.sin(Math.PI / 6);
  assert(Math.abs(shield.y - (flatY - 70 * 0.92)) < 1e-8);
  assert(Math.abs(ground.y - (flatY - offset * 0.92)) < 1e-8);
  // Opposite corners with different elevations still lie on the same shield plane.
  for (const [px, py] of [[0, 0], [190, 0], [190, 130], [0, 130]]) {
    const point = viewer.isoProject(px, py, 70, 200, 200, false);
    assert(Math.abs(point.y - (200 + (px - 95 + py - 65) * Math.sin(Math.PI / 6) - 70 * 0.92)) < 1e-8);
  }
  assert(viewer.terrainRing(f.polygons[0][0]).length > f.polygons[0][0].length);
});

test('Large selections bound elevation requests rather than loading unbounded tiles', async () => {
  const surface = new TerrainSurface();
  const calls = [];
  surface.loadTile = async (...args) => { calls.push(args); };
  assert(await surface.loadBounds(0, 0, 256, 256));
  assert(calls.length <= 16);
  surface.loadTile = async () => { throw new Error('offline'); };
  assert.equal(await surface.loadBounds(100, 100, 100.001, 100.001), false);
});

test('applyTimelineSnapshot interpolates terrain evolution across rotation phases', () => {
  const baseResult = {
    date: '2026-11-01',
    plan_simulation: true,
    cells_count: 1,
    cells: [{
      cell_id: '0_0',
      geometry,
      longitude: -75.209,
      latitude: -12.061,
      altitude_m: 3250,
      soil_water_mm: 100,
      biomass_t_ha: 0.2,
      canopy_cover_pct: 8.6,
      h_current_mm: 400,
      accumulated_erosion_mm: 0,
      soil_color_rgb: [90, 62, 34],
      base_soil_color_rgb: [101, 67, 33],
      shield_enabled: true,
      hourly_environmental_index: [0.5, 0.6],
      hourly_air_temps: [12, 18],
      hourly_canopy_temps: [11, 16],
      lissajous_area: 10,
      mean_canopy_temp: 13.5,
      eta_nutrientes: 0.7,
      is_irrigation_needed: false,
      suggested_irrigation_mm: 0,
    }],
    timeline_snapshots: [
      {
        date: '2026-11-01',
        day_index: 0,
        phase_index: 0,
        phase: 'cultivo',
        crop: 'Potato',
        crop_id: 'papa',
        lot_mean_soil_water_mm: 100,
        lot_mean_n_kg_ha: 100,
        lot_mean_p_kg_ha: 40,
        lot_mean_k_kg_ha: 120,
        lot_mean_biomass_t_ha: 0.2,
        lot_mean_canopy_cover_pct: 8.6,
        lot_mean_h_mm: 400,
        lot_mean_accumulated_erosion_mm: 0,
        lot_mean_temp: 13.5,
        lot_mean_eta_nutrientes: 0.7,
        irrigation_alert: false,
        suggested_irrigation_mm: 0,
        cells: [{
          soil_water_mm: 100,
          nutrientes_n_kg_ha: 100,
          nutrientes_p_kg_ha: 40,
          nutrientes_k_kg_ha: 120,
          biomass_t_ha: 0.2,
          canopy_cover_pct: 8.6,
          ndvi_satelital: 0.21,
          h_current_mm: 400,
          accumulated_erosion_mm: 0,
          soil_color_rgb: [90, 62, 34],
          base_soil_color_rgb: [101, 67, 33],
          shield_enabled: true,
          hourly_environmental_index: [0.5, 0.6],
          hourly_air_temps: [12, 18],
          hourly_canopy_temps: [11, 16],
          lissajous_area: 10,
          mean_canopy_temp: 13.5,
          eta_nutrientes: 0.7,
          water_condition_index: 0.9,
          is_irrigation_needed: false,
          suggested_irrigation_mm: 0,
        }],
      },
      {
        date: '2026-11-11',
        day_index: 10,
        phase_index: 0,
        phase: 'cultivo',
        crop: 'Potato',
        crop_id: 'papa',
        lot_mean_soil_water_mm: 80,
        lot_mean_n_kg_ha: 90,
        lot_mean_p_kg_ha: 38,
        lot_mean_k_kg_ha: 110,
        lot_mean_biomass_t_ha: 6.2,
        lot_mean_canopy_cover_pct: 93.8,
        lot_mean_h_mm: 399.4,
        lot_mean_accumulated_erosion_mm: 0.6,
        lot_mean_temp: 15.5,
        lot_mean_eta_nutrientes: 0.6,
        irrigation_alert: true,
        suggested_irrigation_mm: 12,
        cells: [{
          soil_water_mm: 80,
          nutrientes_n_kg_ha: 90,
          nutrientes_p_kg_ha: 38,
          nutrientes_k_kg_ha: 110,
          biomass_t_ha: 6.2,
          canopy_cover_pct: 93.8,
          ndvi_satelital: 0.81,
          h_current_mm: 399.4,
          accumulated_erosion_mm: 0.6,
          soil_color_rgb: [50, 140, 68],
          base_soil_color_rgb: [101, 67, 33],
          shield_enabled: true,
          hourly_environmental_index: [0.7, 0.8],
          hourly_air_temps: [14, 20],
          hourly_canopy_temps: [13, 18],
          lissajous_area: 20,
          mean_canopy_temp: 15.5,
          eta_nutrientes: 0.6,
          water_condition_index: 0.7,
          is_irrigation_needed: true,
          suggested_irrigation_mm: 12,
        }],
      },
    ],
  };

  const mid = applyTimelineSnapshot(baseResult, '2026-11-06');
  assert.equal(mid.date, '2026-11-06');
  assert.equal(mid.lot_mean_biomass_t_ha, 3.2);
  assert.equal(mid.cells[0].soil_water_mm, 90);
  assert.deepEqual(mid.cells[0].soil_color_rgb, [70, 101, 51]);
});
