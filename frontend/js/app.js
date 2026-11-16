/**
 * AgroPhasor - Main Application (Bootstrap)
 */

import { LotesManager } from './lotes.js';
import { MapManager } from './map.js';
import { ApiService } from './api.js';
import { UIManager } from './ui.js';
import { Escudo3DViewer } from './escudo3d.js';
import { TerrainSurface } from './terrain.js';

document.addEventListener('DOMContentLoaded', () => {
  console.log("Starting AgroPhasor...");

  const lotesManager = new LotesManager();
  const apiService = new ApiService();
  const mapManager = new MapManager('map', lotesManager);
  const terrain = new TerrainSurface();
  mapManager.terrain = terrain;
  mapManager.init();

  const escudo3d = new Escudo3DViewer('escudo-canvas');

  escudo3d.terrain = terrain;
  const syncParcel = () => {
    terrain.setParcel(lotesManager.getSelected()?.geometry);
    mapManager.gridLayer.redraw();
    escudo3d.setParcelGeometry(lotesManager.getSelected()?.geometry, mapManager.map.getZoom());
  };
  lotesManager.subscribe(syncParcel);
  mapManager.map.on('zoomend', syncParcel);

  const uiManager = new UIManager({
    lotesManager,
    mapManager,
    apiService,
    escudo3d
  });
  uiManager.init();

  // Expose globally for console debugging and testing
  window.agroPhasor = {
    lotesManager,
    mapManager,
    apiService,
    uiManager,
    escudo3d
  };

  console.log("AgroPhasor initialized successfully with 2.5D Shield viewer.");
});
