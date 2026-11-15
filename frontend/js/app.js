/**
 * AgroPhasor - Aplicación Principal (Bootstrap)
 */

import { LotesManager } from './lotes.js';
import { MapManager } from './map.js';
import { ApiService } from './api.js';
import { UIManager } from './ui.js';
import { Escudo3DViewer } from './escudo3d.js';

document.addEventListener('DOMContentLoaded', () => {
  console.log("Iniciando AgroPhasor...");

  const lotesManager = new LotesManager();
  const apiService = new ApiService();
  const mapManager = new MapManager('map', lotesManager);
  mapManager.init();

  const escudo3d = new Escudo3DViewer('escudo-canvas');

  const uiManager = new UIManager({
    lotesManager,
    mapManager,
    apiService,
    escudo3d
  });
  uiManager.init();

  // Exponer a nivel global para depuración y pruebas desde consola
  window.agroPhasor = {
    lotesManager,
    mapManager,
    apiService,
    uiManager,
    escudo3d
  };

  console.log("AgroPhasor inicializado con éxito con visor de Escudo 2.5D.");
});
