/**
 * AgroPhasor - Interfaz de Usuario y Recorrido del Agricultor
 * Pasos: 1. Parcela -> 2. Calendario -> 3. Cultivos -> 4. Diagnóstico -> 5. Rotación
 */

import { CONFIG } from './config.js';
import { AgroPhysicsEngine } from './physics.js';

export class UIManager {
  constructor({ lotesManager, mapManager, apiService, escudo3d }) {
    this.lotesManager = lotesManager;
    this.mapManager = mapManager;
    this.apiService = apiService;
    this.escudo3d = escudo3d;
    this.physicsEngine = new AgroPhysicsEngine();

    this.activeStep = 1;
    this.activeTab = "map"; // Para móvil: "map" | "panel"
    this.activePeriod = "P1";
    this.activePriorityMode = "balance_optimo"; // "maxima_resiliencia" | "balance_optimo" | "mayor_ganancia"

    // Controles interactivos What-If del modelo físico
    this.whatIfControls = {
      deltaP0: 0,
      deltaText: 0,
      slopeTheta: 8,
      irrigationI: 0,
      fertN: 90,
      fertP: 35,
      fertK: 180,
      rRes: 0.35,
      stage: "cultivo"
    };

    // Modo de auto-equilibrio interactivo entre perillas
    this.autoBalance = true;

    // Elementos DOM
    this.elements = {};
  }

  init() {
    this.cacheDOMElements();
    this.bindEvents();
    this.renderCropCatalog();
    this.renderPeriods();
    this.setupLotesSubscription();
    this.setupPlaceSearch();
    this.checkBackendStatus();
    this.setupWhatIfControls();
    this.recalculatePhysicalModel();

    // Actualizar iconos Lucide si están presentes
    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  cacheDOMElements() {
    this.elements = {
      // Navegación de pasos
      stepTabs: document.querySelectorAll('.step-tab'),
      stepContents: document.querySelectorAll('.step-content'),
      
      // Contenedores móviles
      viewToggleButtons: document.querySelectorAll('.mobile-view-toggle button'),
      mapContainer: document.getElementById('map-wrapper'),
      panelContainer: document.getElementById('panel-wrapper'),
      
      // Panel de lotes
      lotesList: document.getElementById('lotes-list'),
      btnAddLote: document.getElementById('btn-add-lote'),
      btnConfirmLote: document.getElementById('btn-confirm-lote'),
      btnEditLote: document.getElementById('btn-edit-lote'),
      btnDeleteLote: document.getElementById('btn-delete-lote'),
      btnZoomLote: document.getElementById('btn-zoom-lote'),
      btnStep1Shield: document.getElementById('btn-step1-shield'),
      btnMapShield: document.getElementById('btn-map-shield'),
      
      // Estadísticas del lote activo
      statLoteName: document.getElementById('stat-lote-name'),
      statLoteAreaHa: document.getElementById('stat-lote-area-ha'),
      statLoteAreaM2: document.getElementById('stat-lote-area-m2'),
      statLotePerimeter: document.getElementById('stat-lote-perimeter'),
      statLoteStatusBadge: document.getElementById('stat-lote-status-badge'),
      statLoteCentroid: document.getElementById('stat-lote-centroid'),

      // Simulación & Envío
      btnSimulate: document.getElementById('btn-simulate'),
      checkSimulateError: document.getElementById('check-simulate-error'),
      btnViewGeojson: document.getElementById('btn-view-geojson'),
      backendStatusBadge: document.getElementById('backend-status-badge'),
      
      // Modal GeoJSON
      geojsonModal: document.getElementById('geojson-modal'),
      geojsonCode: document.getElementById('geojson-code'),
      btnCloseModal: document.getElementById('btn-close-modal'),
      btnCopyGeojson: document.getElementById('btn-copy-geojson'),

      // Calendario & Periodos
      periodsContainer: document.getElementById('periods-container'),
      btnAddPeriod: document.getElementById('btn-add-period'),

      // Catálogo de cultivos
      cropCatalogContainer: document.getElementById('crop-catalog-container'),

      // Modos de simulación
      priorityButtons: document.querySelectorAll('.priority-btn'),

      // Indicadores
      indicatorW: document.getElementById('ind-humedad-w'),
      indicatorT: document.getElementById('ind-temp-t'),
      indicatorNPK: document.getElementById('ind-npk'),
      indicatorH: document.getElementById('ind-espesor-h'),
      indicatorShield: document.getElementById('ind-escudo'),

      // Perillas What-If del modelo físico
      checkAutoBalance: document.getElementById('check-auto-balance'),
      sliderDeltaP: document.getElementById('slider-delta-p'),
      valDeltaP: document.getElementById('val-delta-p'),
      sliderDeltaT: document.getElementById('slider-delta-t'),
      valDeltaT: document.getElementById('val-delta-t'),
      sliderSlopeTheta: document.getElementById('slider-slope-theta'),
      valSlopeTheta: document.getElementById('val-slope-theta'),
      lblErosionRate: document.getElementById('lbl-erosion-rate'),
      txtSinkingInfo: document.getElementById('txt-sinking-info'),

      sliderIrrigation: document.getElementById('slider-irrigation'),
      valIrrigation: document.getElementById('val-irrigation'),
      sliderFertN: document.getElementById('slider-fert-n'),
      valFertN: document.getElementById('val-fert-n'),
      sliderFertP: document.getElementById('slider-fert-p'),
      valFertP: document.getElementById('val-fert-p'),
      sliderFertK: document.getElementById('slider-fert-k'),
      valFertK: document.getElementById('val-fert-k'),
      sliderRRes: document.getElementById('slider-r-res'),
      valRRes: document.getElementById('val-r-res'),

      btnStageCrop: document.getElementById('btn-stage-crop'),
      btnStageTrans: document.getElementById('btn-stage-trans'),
      valStageText: document.getElementById('val-stage-text'),
      visorStageTag: document.getElementById('visor-stage-tag'),

      // Salud química Liebig
      valLiebigPct: document.getElementById('val-liebig-pct'),
      liebigBarFill: document.getElementById('liebig-bar-fill'),
      liebigLimitingBadge: document.getElementById('liebig-limiting-badge'),
      pillNpkN: document.getElementById('pill-npk-n'),
      pillNpkP: document.getElementById('pill-npk-p'),
      pillNpkK: document.getElementById('pill-npk-k'),

      // Alertas de Riego
      irrigationAlertCard: document.getElementById('irrigation-alert-card'),
      badgeIrrigationStatus: document.getElementById('badge-irrigation-status'),
      valWcrit: document.getElementById('val-wcrit'),
      valTauAviso: document.getElementById('val-tau-aviso'),
      valIsugerido: document.getElementById('val-isugerido'),
      btnApplyIrrigationSuggested: document.getElementById('btn-apply-irrigation-suggested'),

      // Confianza Montecarlo y Estados del Escudo
      valMontecarloConf: document.getElementById('val-montecarlo-conf'),
      pillAzul: document.getElementById('pill-azul'),
      pillVioleta: document.getElementById('pill-violeta'),
      pillRojo: document.getElementById('pill-rojo'),
      pillDesactivado: document.getElementById('pill-desactivado'),

      // Rotación
      rotationTableBody: document.getElementById('rotation-table-body'),
      rotationReason: document.getElementById('rotation-reason'),
      btnApplySuggestion: document.getElementById('btn-apply-suggestion'),

      // Notificaciones y alertas
      toastContainer: document.getElementById('toast-container'),
      locationInfo: document.getElementById('location-info'),
      btnLocateMe: document.getElementById('btn-locate-me'),
      btnLayerToggle: document.getElementById('btn-layer-toggle')
    };
  }

  bindEvents() {
    // 1. Navegación por pasos
    this.elements.stepTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const step = parseInt(tab.dataset.step, 10);
        this.goToStep(step);
      });
    });

    // 2. Alternar vista móvil (Mapa vs Panel)
    this.elements.viewToggleButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        this.switchMobileView(view);
      });
    });

    // 3. Botones de gestión de lotes
    if (this.elements.btnAddLote) {
      this.elements.btnAddLote.addEventListener('click', () => {
        try {
          if (this.lotesManager.getAll().length >= CONFIG.LIMITS.MAX_LOTES) {
            this.showToast(`Límite de zonas alcanzado (máximo ${CONFIG.LIMITS.MAX_LOTES} zonas para esta entrega).`, "warning");
            return;
          }
          this.mapManager.startDrawPolygon();
          this.switchMobileView("map");
          this.showToast("Dibuja tu parcela en el mapa tocando los puntos del terreno.", "info");
        } catch (e) {
          this.showToast(e.message, "error");
        }
      });
    }

    if (this.elements.btnConfirmLote) {
      this.elements.btnConfirmLote.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (!selected) {
          this.showToast("Primero dibuja o selecciona una parcela en el mapa.", "warning");
          return;
        }
        this.lotesManager.confirmLote(selected.id);
        this.showToast(`¡Contorno de "${selected.name}" confirmado exitosamente!`, "success");
      });
    }

    if (this.elements.btnEditLote) {
      this.elements.btnEditLote.addEventListener('click', () => {
        this.mapManager.startEditMode();
        this.switchMobileView("map");
        this.showToast("Modo edición activado: arrastra los vértices para ajustar el contorno.", "info");
      });
    }

    if (this.elements.btnDeleteLote) {
      this.elements.btnDeleteLote.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (!selected) return;
        if (confirm(`¿Estás seguro de eliminar "${selected.name}"?`)) {
          this.lotesManager.removeLote(selected.id);
          this.showToast("Lote eliminado.", "info");
        }
      });
    }

    if (this.elements.btnZoomLote) {
      this.elements.btnZoomLote.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (selected) {
          this.mapManager.zoomToLote(selected.id);
          this.switchMobileView("map");
        }
      });
    }

    // Botones para ver el Escudo 2.5D
    const openEscudoView = () => {
      this.goToStep(4);
      this.switchMobileView("panel");
      this.showToast("🛡️ Gemelo Digital 2.5D: Malla del escudo protector suspendida sobre tus cultivos.", "info");
    };

    if (this.elements.btnStep1Shield) {
      this.elements.btnStep1Shield.addEventListener('click', openEscudoView);
    }

    if (this.elements.btnMapShield) {
      this.elements.btnMapShield.addEventListener('click', openEscudoView);
    }

    // 4. Botón de Simulación principal (con Resiliencia de Selección ante fallos)
    if (this.elements.btnSimulate) {
      this.elements.btnSimulate.addEventListener('click', () => this.handleSimulation());
    }

    // Checkbox de forzar error para demostrar resiliencia
    if (this.elements.checkSimulateError) {
      this.elements.checkSimulateError.addEventListener('change', (e) => {
        this.apiService.forceFailureForTesting = e.target.checked;
        if (e.target.checked) {
          this.showToast("Modo de prueba de error activado: La siguiente simulación fallará para verificar que tu selección se conserva.", "warning");
        }
      });
    }

    // 5. Modal de GeoJSON
    if (this.elements.btnViewGeojson) {
      this.elements.btnViewGeojson.addEventListener('click', () => {
        const payload = this.lotesManager.toSimulationPayload({ mode: this.activePriorityMode });
        this.elements.geojsonCode.textContent = JSON.stringify(payload, null, 2);
        this.elements.geojsonModal.classList.remove('hidden');
      });
    }

    if (this.elements.btnCloseModal) {
      this.elements.btnCloseModal.addEventListener('click', () => {
        this.elements.geojsonModal.classList.add('hidden');
      });
    }

    if (this.elements.btnCopyGeojson) {
      this.elements.btnCopyGeojson.addEventListener('click', () => {
        navigator.clipboard.writeText(this.elements.geojsonCode.textContent).then(() => {
          this.showToast("GeoJSON copiado al portapapeles", "success");
        });
      });
    }

    // 6. Botón de geolocalización
    if (this.elements.btnLocateMe) {
      this.elements.btnLocateMe.addEventListener('click', () => {
        this.showToast("Buscando tu ubicación… Si aparece una solicitud, selecciona «Permitir».", "info");
        this.mapManager.locateUser(
          (coords) => {
            const acc = Number.isFinite(coords?.accuracy) ? ` (±${Math.ceil(coords.accuracy)} m)` : "";
            this.showToast(`Ubicación encontrada en el mapa${acc}.`, "success");
          },
          (err) => {
            this.showToast(err?.message || "No se pudo obtener la señal GPS; manteniéndote en Valle del Mantaro.", "warning", 6000);
          }
        );
      });
    }

    // 7. Alternar capa satelital
    if (this.elements.btnLayerToggle) {
      this.elements.btnLayerToggle.addEventListener('click', () => {
        const nextLayer = this.mapManager.activeBaseLayer === "esriSatellite" ? "osm" : "esriSatellite";
        this.mapManager.toggleBaseLayer(nextLayer);
        this.elements.btnLayerToggle.textContent = nextLayer === "esriSatellite" ? "🛰️ Satélite" : "🗺️ Mapa Callejero";
      });
    }

    // 8. Modos de prioridad
    this.elements.priorityButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        this.elements.priorityButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.activePriorityMode = btn.dataset.mode;
        this.showToast(`Modo cambiado a: ${btn.textContent.trim()}`, "info");
        // Si ya hay simulación previa, reutilizarla sin re-simular según hito CC-08
        if (this.apiService.lastSimulationResult) {
          this.renderSimulationResults(this.apiService.lastSimulationResult);
        }
      });
    });

    // 9. Aplicar rotación sugerida
    if (this.elements.btnApplySuggestion) {
      this.elements.btnApplySuggestion.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (selected) {
          selected.cultivo_asignado = "habas_verdes";
          this.lotesManager.updateLote(selected.id, { cultivo_asignado: "habas_verdes" });
          this.showToast("¡Rotación sugerida aplicada a tu parcela!", "success");
          this.goToStep(3); // Ir a ver cultivos
        }
      });
    }

    // 10. Agregar periodo
    if (this.elements.btnAddPeriod) {
      this.elements.btnAddPeriod.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (!selected) return;
        const newPIndex = selected.periodos.length + 1;
        selected.periodos.push({
          id: `P${newPIndex}`,
          name: `Campaña ${newPIndex}`,
          start: "Oct",
          end: "Dic",
          cropId: "avena_forrajera"
        });
        this.lotesManager.updateLote(selected.id, { periodos: selected.periodos });
        this.renderPeriods();
        this.showToast(`Periodo P${newPIndex} agregado al calendario.`, "success");
      });
    }
  }

  /**
   * Configurar el buscador de localidades sobre el mapa (/api/places)
   */
  setupPlaceSearch() {
    const form = document.getElementById('place-search');
    const input = document.getElementById('place-query');
    const status = document.getElementById('search-status');
    const results = document.getElementById('search-results');
    if (!form || !input || !status || !results) return;

    const button = form.querySelector('button[type="submit"]');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (button.disabled) return;
      const query = input.value.trim();
      if (query.length < 2) {
        status.textContent = "Escribe al menos dos caracteres.";
        return;
      }

      button.disabled = true;
      results.replaceChildren();
      results.hidden = true;
      status.textContent = "Buscando localidades…";

      try {
        const params = new URLSearchParams({ q: query });
        const response = await fetch(`${this.apiService.baseUrl}${CONFIG.API.PLACES_ENDPOINT}?${params}`);
        if (!response.ok) throw new Error("Place search failed");
        const places = await response.json();

        for (const place of places) {
          const item = document.createElement('li');
          const choice = document.createElement('button');
          choice.type = 'button';
          choice.textContent = place.name;
          choice.addEventListener('click', () => {
            this.mapManager.centerOnPlace(place.lat, place.lon, 15);
            results.hidden = true;
            status.textContent = place.name;
            input.focus();
          });
          item.append(choice);
          results.append(item);
        }

        results.hidden = places.length === 0;
        status.textContent = places.length
          ? "Elige una localidad para centrar el mapa."
          : "No se encontraron localidades. Prueba agregando la región o el país.";
      } catch {
        status.textContent = "El buscador no está disponible por ahora. Puedes navegar por el mapa manualmente.";
      } finally {
        button.disabled = false;
      }
    });
  }

  /**
   * Configurar escuchas de eventos en las perillas de control What-If
   * con soporte de Auto-Equilibrio dinámico entre variables acopladas
   */
  setupWhatIfControls() {
    const el = this.elements;

    // Checkbox de control de auto-equilibrio
    if (el.checkAutoBalance) {
      el.checkAutoBalance.addEventListener('change', (e) => {
        this.autoBalance = e.target.checked;
        if (this.autoBalance) {
          this.balanceWhatIfControls('fertN');
          this.syncSliderInputs();
          this.recalculatePhysicalModel();
        }
        this.showToast(
          this.autoBalance
            ? "⚖️ Auto-Equilibrio ACTIVADO: Las perillas se compensarán mutuamente."
            : "Modo manual: Ajuste independiente por perilla.",
          "info"
        );
      });
    }

    const controls = [
      ['sliderDeltaP', 'deltaP0'], ['sliderDeltaT', 'deltaText'],
      ['sliderSlopeTheta', 'slopeTheta'], ['sliderIrrigation', 'irrigationI'],
      ['sliderFertN', 'fertN'], ['sliderFertP', 'fertP'],
      ['sliderFertK', 'fertK'], ['sliderRRes', 'rRes']
    ];
    for (const [element, key] of controls) {
      el[element]?.addEventListener('input', (event) => {
        this.whatIfControls[key] = Number(event.target.value) / (key === 'rRes' ? 100 : 1);
        if (this.autoBalance) this.balanceWhatIfControls(key);
        this.syncSliderInputs();
        this.recalculatePhysicalModel();
      });
    }

    // Selector de régimen (Cultivo vs Suelo Desnudo)
    if (el.btnStageCrop && el.btnStageTrans) {
      el.btnStageCrop.addEventListener('click', () => {
        this.whatIfControls.stage = "cultivo";
        el.btnStageCrop.classList.add('active');
        el.btnStageTrans.classList.remove('active');
        if (el.valStageText) el.valStageText.textContent = "Cultivo Activo";
        if (el.visorStageTag) el.visorStageTag.textContent = "Cultivo Activo";
        this.recalculatePhysicalModel();
      });

      el.btnStageTrans.addEventListener('click', () => {
        this.whatIfControls.stage = "transicion";
        el.btnStageTrans.classList.add('active');
        el.btnStageCrop.classList.remove('active');
        if (el.valStageText) el.valStageText.textContent = "Suelo Desnudo (Transición)";
        if (el.visorStageTag) el.visorStageTag.textContent = "q = Transición";
        this.recalculatePhysicalModel();
      });
    }

    // Botón de aplicación de riego sugerido
    if (el.btnApplyIrrigationSuggested) {
      el.btnApplyIrrigationSuggested.addEventListener('click', () => {
        const suggested = this.lastSuggestedIrrigation || 25;
        if (el.sliderIrrigation) {
          el.sliderIrrigation.value = suggested;
          this.whatIfControls.irrigationI = suggested;
          if (el.valIrrigation) el.valIrrigation.textContent = `${suggested} mm`;
          this.recalculatePhysicalModel();
          this.showToast(`💧 Riego sugerido de ${suggested} mm aplicado al escenario.`, "success");
        }
      });
    }

    // Clicks en las píldoras de los 4 estados para demostración rápida
    if (el.pillAzul) {
      el.pillAzul.addEventListener('click', () => {
        this.whatIfControls.stage = "cultivo";
        this.whatIfControls.deltaP0 = 0;
        this.whatIfControls.deltaText = 0;
        this.whatIfControls.fertN = 140;
        this.whatIfControls.fertP = 75;
        this.whatIfControls.fertK = 210;
        this.whatIfControls.irrigationI = 20;
        this.whatIfControls.rRes = 0.50;
        this.syncSliderInputs();
        this.recalculatePhysicalModel();
        this.showToast("Estado activado: 🔵 Azul Cobalto (Óptima Resiliencia, Ψ > 0.70)", "info");
      });
    }

    if (el.pillVioleta) {
      el.pillVioleta.addEventListener('click', () => {
        this.whatIfControls.stage = "cultivo";
        this.whatIfControls.deltaP0 = -25;
        this.whatIfControls.deltaText = 2.5;
        this.whatIfControls.fertN = 70;
        this.whatIfControls.irrigationI = 0;
        this.syncSliderInputs();
        this.recalculatePhysicalModel();
        this.showToast("Estado activado: 🟣 Violeta / Ámbar (Estrés Moderado, Ψ ≈ 0.50)", "warning");
      });
    }

    if (el.pillRojo) {
      el.pillRojo.addEventListener('click', () => {
        this.whatIfControls.stage = "cultivo";
        this.whatIfControls.deltaP0 = -45;
        this.whatIfControls.deltaText = 4.5;
        this.whatIfControls.slopeTheta = 24;
        this.whatIfControls.fertN = 25;
        this.whatIfControls.fertP = 15;
        this.whatIfControls.irrigationI = 0;
        this.whatIfControls.rRes = 0.05;
        this.syncSliderInputs();
        this.recalculatePhysicalModel();
        this.showToast("Estado activado: 🔴 Rojo Intenso (Estrés Crítico / Colapso, Ψ < 0.38)", "error");
      });
    }

    if (el.pillDesactivado) {
      el.pillDesactivado.addEventListener('click', () => {
        this.whatIfControls.stage = "transicion";
        this.syncSliderInputs();
        this.recalculatePhysicalModel();
        this.showToast("Estado activado: ⚪ Escudo Desactivado (q = Transición, suelo desnudo)", "info");
      });
    }
  }

  // Compensar con manejo sin modificar el clima ni la pendiente elegidos.
  balanceWhatIfControls(changed) {
    const c = this.whatIfControls;
    const set = (key, value, min, max, step) => {
      c[key] = Number(Math.max(min, Math.min(max, Math.round(value / step) * step)).toFixed(2));
    };
    const nutrients = { fertN: 150, fertP: 80, fertK: 220 };
    if (changed in nutrients) {
      const ratio = c[changed] / nutrients[changed];
      for (const [key, optimal] of Object.entries(nutrients)) {
        if (key !== changed) set(key, optimal * ratio, 0,
          { fertN: 180, fertP: 120, fertK: 240 }[key], key === 'fertK' ? 10 : 5);
      }
    }
    const erosionCover = (20 + c.slopeTheta / 35 * 65 + Math.max(0, c.deltaP0) * 0.2) / 100;
    if (changed !== 'rRes') {
      const waterCover = changed === 'irrigationI'
        ? (8 + c.deltaText * 0.4 - c.deltaP0 * 0.35 - c.irrigationI) / 2 : 0;
      set('rRes', Math.max(erosionCover, waterCover), 0, 1, 0.05);
    }
    if (changed !== 'irrigationI') {
      const evaporation = 8 * (1 + c.deltaText * 0.05 - c.rRes * 0.25);
      set('irrigationI', evaporation - c.deltaP0 * 0.35, 0, 60, 5);
    }
  }

  syncSliderInputs() {
    const el = this.elements;
    const c = this.whatIfControls;
    if (el.sliderDeltaP) { el.sliderDeltaP.value = c.deltaP0; el.valDeltaP.textContent = `${c.deltaP0 >= 0 ? '+' : ''}${c.deltaP0}%`; }
    if (el.sliderDeltaT) { el.sliderDeltaT.value = c.deltaText; el.valDeltaT.textContent = `${c.deltaText >= 0 ? '+' : ''}${c.deltaText} °C`; }
    if (el.sliderSlopeTheta) { el.sliderSlopeTheta.value = c.slopeTheta; el.valSlopeTheta.textContent = `${c.slopeTheta}°`; }
    if (el.sliderIrrigation) { el.sliderIrrigation.value = c.irrigationI; el.valIrrigation.textContent = `${c.irrigationI} mm`; }
    if (el.sliderFertN) { el.sliderFertN.value = c.fertN; el.valFertN.textContent = `${c.fertN} kg/ha`; }
    if (el.sliderFertP) { el.sliderFertP.value = c.fertP; el.valFertP.textContent = `${c.fertP} kg/ha`; }
    if (el.sliderFertK) { el.sliderFertK.value = c.fertK; el.valFertK.textContent = `${c.fertK} kg/ha`; }
    if (el.sliderRRes) { el.sliderRRes.value = c.rRes * 100; el.valRRes.textContent = `${Math.round(c.rRes * 100)}%`; }

    if (c.stage === "cultivo") {
      el.btnStageCrop?.classList.add('active');
      el.btnStageTrans?.classList.remove('active');
      if (el.valStageText) el.valStageText.textContent = "Cultivo Activo";
    } else {
      el.btnStageTrans?.classList.add('active');
      el.btnStageCrop?.classList.remove('active');
      if (el.valStageText) el.valStageText.textContent = "Suelo Desnudo (Transición)";
    }
  }

  /**
   * Recalcular el modelo físico dinámico y sincronizar interfaz y visor 2.5D
   */
  recalculatePhysicalModel() {
    const el = this.elements;
    const phys = this.physicsEngine.evaluate(this.whatIfControls);

    if (this.mapManager.terrain) {
      this.mapManager.terrain.controls = { ...this.whatIfControls };
      this.mapManager.terrain.physics = phys;
      // Agrupar eventos rápidos de las perillas en un único redibujado.
      clearTimeout(this.terrainRedrawTimer);
      this.terrainRedrawTimer = setTimeout(() => this.mapManager.gridLayer?.redraw(), 80);
    }

    // 1. Actualizar visor 2.5D de Cerros en Cuadrado + Escudo Plano
    if (this.escudo3d) {
      this.escudo3d.updatePhysicsState(phys);
    }

    // 2. Información de erosión y hundimiento
    if (el.lblErosionRate) el.lblErosionRate.textContent = `${phys.erosionRateMmYear} mm/año`;
    if (el.txtSinkingInfo) el.txtSinkingInfo.innerHTML = `Hundimiento por erosión: <strong>${phys.erosionSinkingMm} mm</strong>`;

    // 3. Salud Química por Ley de Liebig
    if (el.valLiebigPct) el.valLiebigPct.textContent = `${Math.round(phys.eta_nutrientes * 100)}%`;
    if (el.liebigBarFill) {
      el.liebigBarFill.style.width = `${Math.round(phys.eta_nutrientes * 100)}%`;
      el.liebigBarFill.style.boxShadow = `0 0 12px ${phys.eta_nutrientes > 0.65 ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)'}`;
    }

    if (el.liebigLimitingBadge) {
      el.liebigLimitingBadge.innerHTML = `<span>⚠️ Crecimiento limitado por <strong>${phys.limitingNutrient}</strong> según Ley de Liebig</span>`;
    }

    // Actualizar píldoras NPK
    if (el.pillNpkN) {
      el.pillNpkN.textContent = `N: ${Math.round(phys.eta_N * 100)}%`;
      el.pillNpkN.className = `npk-pill ${phys.limitingNutrient.startsWith('N') ? 'limiting' : ''}`;
    }
    if (el.pillNpkP) {
      el.pillNpkP.textContent = `P: ${Math.round(phys.eta_P * 100)}%`;
      el.pillNpkP.className = `npk-pill ${phys.limitingNutrient.startsWith('P') ? 'limiting' : ''}`;
    }
    if (el.pillNpkK) {
      el.pillNpkK.textContent = `K: ${Math.round(phys.eta_K * 100)}%`;
      el.pillNpkK.className = `npk-pill ${phys.limitingNutrient.startsWith('K') ? 'limiting' : ''}`;
    }

    // 4. Alertas de Riego
    this.lastSuggestedIrrigation = phys.irrigationAlert.Isugerido;
    if (el.valWcrit) el.valWcrit.textContent = `${phys.irrigationAlert.W_crit} mm`;
    if (el.valTauAviso) el.valTauAviso.textContent = `${phys.irrigationAlert.tauAviso} días`;
    if (el.valIsugerido) el.valIsugerido.textContent = `${phys.irrigationAlert.Isugerido} mm`;

    if (el.irrigationAlertCard) {
      el.irrigationAlertCard.classList.toggle('alert-active', phys.irrigationAlert.active);
    }
    if (el.badgeIrrigationStatus) {
      if (phys.irrigationAlert.active) {
        el.badgeIrrigationStatus.textContent = "⚠️ Estrés Hídrico Inminente";
        el.badgeIrrigationStatus.className = "gap-badge gap-gap";
      } else {
        el.badgeIrrigationStatus.textContent = "Humedad Adecuada";
        el.badgeIrrigationStatus.className = "gap-badge gap-obs";
      }
    }

    // 5. Confianza Montecarlo
    if (el.valMontecarloConf) el.valMontecarloConf.textContent = `${phys.montecarloConfidence}%`;

    // 6. Sincronizar Píldoras de los 4 Estados del Escudo
    const s = phys.shieldState;
    el.pillAzul?.classList.toggle('active-azul', s === 'azul_cobalto');
    el.pillVioleta?.classList.toggle('active-violeta', s === 'violeta_ambar');
    el.pillRojo?.classList.toggle('active-rojo', s === 'rojo_intenso');
    el.pillDesactivado?.classList.toggle('active-desactivado', s === 'desactivado');

    // 7. Actualizar Indicadores Escalares
    if (el.indicatorW) {
      el.indicatorW.innerHTML = `
        <div class="stat-value" style="color: ${phys.W < 95 ? '#ef4444' : '#10b981'}">${phys.W} <small>mm</small></div>
        <div class="stat-label">Humedad en raíces (W)</div>
        <div class="stat-badge ${phys.W < 95 ? 'badge-amber' : 'badge-green'}">${phys.W < 95 ? 'Alerta estrés' : 'Adecuado'}</div>
      `;
    }

    if (el.indicatorT) {
      el.indicatorT.innerHTML = `
        <div class="stat-value" style="color: ${phys.T > 22 || phys.T < 10 ? '#f59e0b' : '#38bdf8'}">${phys.T} <small>°C</small></div>
        <div class="stat-label">Temperatura dosel (T)</div>
        <div class="stat-badge ${phys.T > 22 ? 'badge-amber' : 'badge-blue'}">${phys.T > 22 ? 'Estrés térmico' : 'Óptimo'}</div>
      `;
    }

    if (el.indicatorH) {
      el.indicatorH.innerHTML = `
        <div class="stat-value">${phys.H} <small>mm</small></div>
        <div class="stat-label">Capa fértil (H)</div>
        <div class="stat-badge ${phys.erosionRateMmYear > 2 ? 'badge-amber' : 'badge-green'}">${phys.erosionRateMmYear} mm/año</div>
      `;
    }

    if (el.indicatorNPK) {
      el.indicatorNPK.innerHTML = `
        <div class="stat-value">N:${this.whatIfControls.fertN} P:${this.whatIfControls.fertP} K:${this.whatIfControls.fertK}</div>
        <div class="stat-label">Dosis NPK kg/ha</div>
        <div class="stat-badge badge-amber">${phys.limitingNutrient}</div>
      `;
    }
  }

  /**
   * Ejecución de la simulación con preservación estricta de la selección
   */
  async handleSimulation() {
    const selected = this.lotesManager.getSelected();
    if (!selected) {
      this.showToast("Selecciona o dibuja una parcela primero.", "warning");
      this.goToStep(1);
      return;
    }

    // 1. Marcar estado "Confirmado" si estaba en borrador
    this.lotesManager.confirmLote(selected.id);

    // 2. Preparar el payload de GeoJSON para el servidor
    const payload = this.lotesManager.toSimulationPayload({
      mode: this.activePriorityMode
    });

    // 3. UI en estado de carga
    this.elements.btnSimulate.disabled = true;
    this.elements.btnSimulate.innerHTML = `<span class="spinner"></span> Simulando respuesta del terreno...`;

    const selectedIdBefore = selected.id;

    try {
      this.showToast("Enviando coordenadas GeoJSON al servidor...", "info");
      
      // Llamada al API (con opción de usar respaldo si el servidor no está en línea)
      const results = await this.apiService.runSimulation(payload, {
        useOfflineFallback: true
      });

      // Validar que se conserve la selección activa
      this.lotesManager.select(selectedIdBefore);

      // Mostrar resultados
      this.renderSimulationResults(results);

      if (results._is_fallback) {
        this.showToast("⚠️ Servidor backend en desarrollo. Se utilizaron datos físicos de respaldo (NASA POWER Mantaro). Tu parcela sigue seleccionada.", "warning", 6000);
      } else {
        this.showToast("✅ Simulación completada con éxito.", "success");
      }

      // Avanzar al paso 4 (Diagnóstico) para ver los resultados
      this.goToStep(4);

    } catch (err) {
      console.error("Error en simulación:", err);

      // REQUISITO CRÍTICO: CONSERVAR LA SELECCIÓN SI FALLA LA SIMULACIÓN
      // Garantizar que el lote continúe seleccionado tanto en datos como en mapa
      if (selectedIdBefore) {
        this.lotesManager.select(selectedIdBefore);
      }

      const isTest = err.isSimulatedTest;
      const errorTitle = isTest 
        ? "⚠️ Prueba de Resiliencia: La simulación falló intencionalmente." 
        : "⚠️ No se pudo completar la simulación en el servidor.";
      
      const errorMessage = `${errorTitle} Tu parcela "${selected.name}" y sus coordenadas GeoJSON se conservaron seleccionadas e intactas en tu dispositivo.`;

      this.showToast(errorMessage, "error", 7000);
      this.showPersistentErrorBanner(selected, err.message);

    } finally {
      this.elements.btnSimulate.disabled = false;
      this.elements.btnSimulate.innerHTML = `<span>🚀 Simular Terreno</span>`;
      // Re-verificar estado de selección
      this.updateLoteStats(this.lotesManager.getSelected());
    }
  }

  /**
   * Banner de alerta persistente cuando ocurre un fallo
   */
  showPersistentErrorBanner(lote, reason) {
    const existing = document.getElementById('resilience-error-banner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'resilience-error-banner';
    banner.className = 'resilience-banner';
    banner.innerHTML = `
      <div class="banner-content">
        <span class="banner-icon">🛡️</span>
        <div class="banner-text">
          <strong>Selección Protegida:</strong> La simulación falló (${reason}), pero el <strong>${lote.name}</strong> (${lote.area_ha} ha) sigue seleccionado y no se perdió ningún vértice.
        </div>
        <button class="banner-close" onclick="this.parentElement.parentElement.remove()">✕</button>
      </div>
    `;

    document.querySelector('.app-main').prepend(banner);
  }

  /**
   * Renderizar resultados de la simulación en los indicadores
   */
  renderSimulationResults(data) {
    if (!data || !data.indicadores) return;

    const ind = data.indicadores;

    // Actualizar el modelo visual 2.5D del Escudo
    if (this.escudo3d) {
      this.escudo3d.updateMetrics({
        humedad_W: ind.humedad_radicular_W?.valor,
        temperatura_T: ind.temperatura_dosel_T?.valor,
        espesor_H: ind.espesor_fertil_H?.valor,
        escudoScore: ind.escudo_ambiental?.indice,
        biomasa_B: ind.biomasa_aerea_B?.valor
      });
    }

    // Humedad radicular W
    if (this.elements.indicatorW) {
      this.elements.indicatorW.innerHTML = `
        <div class="stat-value" style="color: ${ind.humedad_radicular_W.color}">${ind.humedad_radicular_W.valor} <small>${ind.humedad_radicular_W.unidad}</small></div>
        <div class="stat-label">Humedad en raíces (W)</div>
        <div class="stat-badge badge-green">${ind.humedad_radicular_W.estado}</div>
      `;
    }

    // Temperatura T
    if (this.elements.indicatorT) {
      this.elements.indicatorT.innerHTML = `
        <div class="stat-value" style="color: ${ind.temperatura_dosel_T.color}">${ind.temperatura_dosel_T.valor} <small>${ind.temperatura_dosel_T.unidad}</small></div>
        <div class="stat-label">Temperatura dosel (T)</div>
        <div class="stat-badge badge-blue">${ind.temperatura_dosel_T.estado}</div>
      `;
    }

    // Nutrientes NPK
    if (this.elements.indicatorNPK) {
      const npk = ind.nutrientes_NPK;
      this.elements.indicatorNPK.innerHTML = `
        <div class="stat-value">N:${npk.N.valor} P:${npk.P.valor} K:${npk.K.valor}</div>
        <div class="stat-label">Nutrientes kg/ha</div>
        <div class="stat-badge badge-amber">${npk.estado_general}</div>
      `;
    }

    // Espesor fértil H
    if (this.elements.indicatorH) {
      this.elements.indicatorH.innerHTML = `
        <div class="stat-value">${ind.espesor_fertil_H.valor} <small>${ind.espesor_fertil_H.unidad}</small></div>
        <div class="stat-label">Capa fértil (H)</div>
        <div class="stat-badge badge-green">${ind.espesor_fertil_H.tasa_erosion}</div>
      `;
    }

    // Escudo ambiental
    if (this.elements.indicatorShield) {
      const shield = ind.escudo_ambiental;
      this.elements.indicatorShield.innerHTML = `
        <div class="stat-value" style="color: ${shield.color}">${shield.indice} <small>/ ${shield.max}</small></div>
        <div class="stat-label">Escudo Ambiental</div>
        <div class="stat-badge badge-green">${shield.calificacion}</div>
      `;
    }

    // Tabla de comparación de rotación
    if (data.rotacion_recomendada && this.elements.rotationTableBody) {
      const rot = data.rotacion_recomendada;
      this.elements.rotationTableBody.innerHTML = rot.sugerencia_optimizada.map(item => `
        <tr>
          <td><strong>${item.periodo}</strong></td>
          <td><span class="crop-pill">${item.cultivo}</span></td>
          <td><small class="text-green">${item.ventaja || item.rendimiento_est || 'Plan base'}</small></td>
        </tr>
      `).join('');

      if (this.elements.rotationReason) {
        this.elements.rotationReason.textContent = rot.motivo_agronomico;
      }
    }
  }

  /**
   * Renderizar catálogo de cultivos inicial
   */
  renderCropCatalog() {
    if (!this.elements.cropCatalogContainer) return;

    this.elements.cropCatalogContainer.innerHTML = CONFIG.CROP_CATALOG.map(crop => `
      <div class="crop-card" data-crop-id="${crop.id}">
        <div class="crop-icon">${crop.icon}</div>
        <div class="crop-info">
          <div class="crop-name">${crop.name}</div>
          <div class="crop-meta">${crop.family} &bull; ${crop.cycle_days} días</div>
          <div class="crop-impact">${crop.soil_impact}</div>
        </div>
        <button class="btn-select-crop" title="Asignar al periodo">Asignar</button>
      </div>
    `).join('');

    // Eventos de selección de cultivo
    this.elements.cropCatalogContainer.querySelectorAll('.crop-card').forEach(card => {
      card.addEventListener('click', () => {
        const cropId = card.dataset.cropId;
        this.assignCropToActivePeriod(cropId);
      });
    });
  }

  assignCropToActivePeriod(cropId) {
    const selectedLote = this.lotesManager.getSelected();
    if (!selectedLote) {
      this.showToast("Primero selecciona un lote.", "warning");
      return;
    }

    const crop = CONFIG.CROP_CATALOG.find(c => c.id === cropId);
    if (!crop) return;

    // Actualizar el periodo activo
    const period = selectedLote.periodos.find(p => p.id === this.activePeriod);
    if (period) {
      period.cropId = cropId;
      period.cropName = crop.name;
    }

    selectedLote.cultivo_asignado = cropId;
    this.lotesManager.updateLote(selectedLote.id, {
      cultivo_asignado: cropId,
      periodos: selectedLote.periodos
    });

    if (this.escudo3d) {
      this.escudo3d.updateMetrics({
        cropName: crop.name,
        cropIcon: crop.icon
      });
    }

    this.renderPeriods();
    this.showToast(`"${crop.name}" asignado a ${this.activePeriod} de ${selectedLote.name}`, "success");
  }

  /**
   * Renderizar el calendario con marcas de mes legibles
   * "una marca por cada mes, con etiquetas como Ene · Feb · Mar"
   */
  renderPeriods() {
    if (!this.elements.periodsContainer) return;

    const selected = this.lotesManager.getSelected();
    const periods = selected ? selected.periodos : [
      { id: "P1", name: "Campaña Chica", start: "Ene", end: "May", cropId: "papa_canchan" },
      { id: "P2", name: "Campaña Grande", start: "Jun", end: "Dic", cropId: "habas_verdes" }
    ];

    const months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"];

    this.elements.periodsContainer.innerHTML = `
      <div class="months-timeline">
        ${months.map(m => `<span class="month-tick">${m}</span>`).join('')}
      </div>
      <div class="periods-cards-list">
        ${periods.map(p => {
          const crop = CONFIG.CROP_CATALOG.find(c => c.id === p.cropId) || CONFIG.CROP_CATALOG[0];
          const isActive = p.id === this.activePeriod;
          return `
            <div class="period-chip ${isActive ? 'active' : ''}" data-period-id="${p.id}">
              <div class="period-chip-header">
                <span class="period-id">${p.id}</span>
                <span class="period-dates">${p.start} &rarr; ${p.end}</span>
              </div>
              <div class="period-crop-name">
                <span>${crop.icon}</span> ${crop.name}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    // Eventos al tocar un periodo
    this.elements.periodsContainer.querySelectorAll('.period-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        this.activePeriod = chip.dataset.periodId;
        this.renderPeriods();
        this.showToast(`Periodo activo: ${this.activePeriod}. Elige un cultivo para asignarlo.`, "info");
      });
    });
  }

  /**
   * Suscribirse a cambios en los lotes
   */
  setupLotesSubscription() {
    this.lotesManager.subscribe((lotes, selected) => {
      this.renderLotesList(lotes, selected);
      this.updateLoteStats(selected);
      this.renderPeriods();
      this.updateParcelEdo1(selected);
    });
    document.getElementById('btn-retry-parcel-edo1').addEventListener('click', () => {
      this.updateParcelEdo1(this.lotesManager.getSelected(), true);
    });
  }

  updateParcelEdo1(selected, retry = false) {
    const key = selected && JSON.stringify([selected.id, selected.geometry, selected.cultivo_asignado]);
    if (!retry && key === this.parcelEdo1Key) return;
    this.parcelEdo1Key = key;
    this.parcelEdo1Request?.abort();
    clearTimeout(this.parcelEdo1Timer);
    this.mapManager.showParcelTemperatures([]);

    const status = document.getElementById('parcel-edo1-status');
    const retryButton = document.getElementById('btn-retry-parcel-edo1');
    retryButton.hidden = true;
    status.textContent = selected ? 'Calculando la temperatura del dosel con NASA POWER y SRTM…' : '';
    if (!selected) return;

    const request = new AbortController();
    this.parcelEdo1Request = request;
    this.parcelEdo1Timer = setTimeout(async () => {
      try {
        const result = await this.apiService.runParcelEdo1(selected, request.signal);
        if (request.signal.aborted) return;
        this.mapManager.showParcelTemperatures(result.cells);
        const crop = result.reference_crop_used ? `${result.crop} (cultivo de referencia)` : result.crop;
        status.textContent = `EDO 1 · ${result.cells_count} celdas de 30 m · Media de dosel ${result.lot_mean_temp} °C · ${result.date} (hora solar local) · ${crop} · Agua radicular asumida: ${result.soil_water_mm} mm`;
      } catch (error) {
        if (request.signal.aborted) return;
        status.textContent = `EDO 1: ${error.name === 'TimeoutError' ? 'La consulta tardó demasiado.' : error.message}`;
        retryButton.hidden = false;
      }
    }, 350);
  }

  renderLotesList(lotes, selected) {
    if (!this.elements.lotesList) return;

    if (lotes.length === 0) {
      this.elements.lotesList.innerHTML = `
        <div class="empty-state">
          <p>No hay lotes dibujados aún.</p>
          <small>Toca el botón "+ Dibujar Lote" para trazar tu parcela con Geoman.</small>
        </div>
      `;
      return;
    }

    this.elements.lotesList.innerHTML = lotes.map(lote => {
      const isSelected = selected && selected.id === lote.id;
      const isConfirmed = lote.status === "confirmed";

      return `
        <div class="lote-card ${isSelected ? 'selected' : ''}" data-lote-id="${lote.id}">
          <div class="lote-card-top">
            <span class="lote-title">${lote.name}</span>
            <span class="status-pill ${isConfirmed ? 'pill-confirmed' : 'pill-draft'}">
              ${isConfirmed ? 'Confirmado' : 'Borrador'}
            </span>
          </div>
          <div class="lote-card-bottom">
            <span><strong>${lote.area_ha}</strong> ha (${lote.area_m2.toLocaleString()} m²)</span>
            <button class="btn-micro-select" title="Seleccionar">${isSelected ? 'Activo' : 'Elegir'}</button>
          </div>
        </div>
      `;
    }).join('');

    // Evento de selección de lote
    this.elements.lotesList.querySelectorAll('.lote-card').forEach(card => {
      card.addEventListener('click', () => {
        const id = card.dataset.loteId;
        this.lotesManager.select(id);
        this.mapManager.zoomToLote(id);
      });
    });
  }

  updateLoteStats(selected) {
    if (!selected) {
      if (this.elements.statLoteName) this.elements.statLoteName.textContent = "Ningún lote seleccionado";
      if (this.elements.statLoteAreaHa) this.elements.statLoteAreaHa.textContent = "0.00 ha";
      if (this.elements.statLoteAreaM2) this.elements.statLoteAreaM2.textContent = "0 m²";
      if (this.elements.statLotePerimeter) this.elements.statLotePerimeter.textContent = "0 m";
      if (this.elements.statLoteStatusBadge) {
        this.elements.statLoteStatusBadge.textContent = "Sin parcela";
        this.elements.statLoteStatusBadge.className = "status-badge badge-neutral";
      }
      return;
    }

    if (this.elements.statLoteName) this.elements.statLoteName.textContent = selected.name;
    if (this.elements.statLoteAreaHa) this.elements.statLoteAreaHa.textContent = `${selected.area_ha} ha`;
    if (this.elements.statLoteAreaM2) this.elements.statLoteAreaM2.textContent = `${selected.area_m2.toLocaleString()} m²`;
    if (this.elements.statLotePerimeter) this.elements.statLotePerimeter.textContent = `${selected.perimeter_m.toLocaleString()} m`;

    if (this.elements.statLoteCentroid && selected.centroid) {
      this.elements.statLoteCentroid.textContent = `${selected.centroid[0]}° S, ${selected.centroid[1]}° W`;
    }

    if (this.elements.statLoteStatusBadge) {
      const isConfirmed = selected.status === "confirmed";
      this.elements.statLoteStatusBadge.textContent = isConfirmed ? "Confirmado" : "Borrador (Sin confirmar)";
      this.elements.statLoteStatusBadge.className = `status-badge ${isConfirmed ? 'badge-green' : 'badge-amber'}`;
    }
  }

  goToStep(stepNumber) {
    this.activeStep = stepNumber;
    this.elements.stepTabs.forEach(tab => {
      tab.classList.toggle('active', parseInt(tab.dataset.step, 10) === stepNumber);
    });
    this.elements.stepContents.forEach(content => {
      content.classList.toggle('active', parseInt(content.dataset.step, 10) === stepNumber);
    });

    // En pantallas móviles, si es paso 1 podemos mostrar el mapa, en otros pasos mostrar panel
    if (window.innerWidth <= 768 && stepNumber !== 1) {
      this.switchMobileView("panel");
    }
  }

  switchMobileView(view) {
    this.activeTab = view;
    this.elements.viewToggleButtons.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === view);
    });

    if (this.elements.mapContainer && this.elements.panelContainer) {
      if (view === "map") {
        this.elements.mapContainer.classList.remove('mobile-hidden');
        this.elements.panelContainer.classList.add('mobile-hidden');
        // Invalidar tamaño del mapa al volver a ser visible
        if (this.mapManager && this.mapManager.map) {
          setTimeout(() => this.mapManager.map.invalidateSize(), 150);
        }
      } else {
        this.elements.mapContainer.classList.add('mobile-hidden');
        this.elements.panelContainer.classList.remove('mobile-hidden');
      }
    }
  }

  async checkBackendStatus() {
    const isOnline = await this.apiService.checkHealth();
    if (this.elements.backendStatusBadge) {
      if (isOnline) {
        this.elements.backendStatusBadge.innerHTML = `<span class="dot-online"></span> Backend Conectado`;
        this.elements.backendStatusBadge.className = "badge-server badge-online";
      } else {
        this.elements.backendStatusBadge.innerHTML = `<span class="dot-offline"></span> Modo Respaldo / Offline`;
        this.elements.backendStatusBadge.className = "badge-server badge-offline";
      }
    }
  }

  showToast(message, type = "info", duration = 4000) {
    if (!this.elements.toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === "success" ? "✅" : type === "warning" ? "⚠️" : type === "error" ? "❌" : "ℹ️";

    toast.innerHTML = `
      <span class="toast-icon">${icon}</span>
      <span class="toast-text">${message}</span>
      <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
    `;

    this.elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('fade-out');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
}
