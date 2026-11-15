/**
 * AgroPhasor - Aplicación Principal (Bootstrap)
 */

import { LotesManager } from './lotes.js';
import { MapManager } from './map.js';
import { ApiService } from './api.js';
import { UIManager } from './ui.js';

document.addEventListener('DOMContentLoaded', () => {
  console.log("Iniciando AgroPhasor...");

  const lotesManager = new LotesManager();
  const apiService = new ApiService();
  const mapManager = new MapManager('map', lotesManager);
  mapManager.init();

  const uiManager = new UIManager({
    lotesManager,
    mapManager,
    apiService
  });
  uiManager.init();

  // Exponer a nivel global para depuración y pruebas desde consola
  window.agroPhasor = {
    lotesManager,
    mapManager,
    apiService,
    uiManager
  };

  console.log("AgroPhasor inicializado con éxito.");
});
