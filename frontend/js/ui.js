/**
 * AgroPhasor - User Interface & Farmer Workflow
 * Steps: 1. Parcel -> 2. Calendar -> 3. Crops -> 4. Diagnostics -> 5. Rotation
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
    this.activeTab = "map"; // For mobile: "map" | "panel"
    this.activePeriod = "P1";
    this.activePriorityMode = "balance_optimo"; // "maxima_resiliencia" | "balance_optimo" | "mayor_ganancia"

    // Interactive What-If physical model controls
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

    // Interactive auto-balance mode across sliders
    this.autoBalance = true;

    // DOM elements
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

    // Initialize Lucide icons if loaded
    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  cacheDOMElements() {
    this.elements = {
      // Step navigation
      stepTabs: document.querySelectorAll('.step-tab'),
      stepContents: document.querySelectorAll('.step-content'),
      
      // Mobile containers
      viewToggleButtons: document.querySelectorAll('.mobile-view-toggle button'),
      mapContainer: document.getElementById('map-wrapper'),
      panelContainer: document.getElementById('panel-wrapper'),
      
      // Lots panel
      lotesList: document.getElementById('lotes-list'),
      btnAddLote: document.getElementById('btn-add-lote'),
      btnConfirmLote: document.getElementById('btn-confirm-lote'),
      btnEditLote: document.getElementById('btn-edit-lote'),
      btnDeleteLote: document.getElementById('btn-delete-lote'),
      btnZoomLote: document.getElementById('btn-zoom-lote'),
      btnStep1Shield: document.getElementById('btn-step1-shield'),
      btnMapShield: document.getElementById('btn-map-shield'),
      
      // Active lot stats
      statLoteName: document.getElementById('stat-lote-name'),
      statLoteAreaHa: document.getElementById('stat-lote-area-ha'),
      statLoteAreaM2: document.getElementById('stat-lote-area-m2'),
      statLotePerimeter: document.getElementById('stat-lote-perimeter'),
      statLoteStatusBadge: document.getElementById('stat-lote-status-badge'),
      statLoteCentroid: document.getElementById('stat-lote-centroid'),

      // Simulation & submission
      btnSimulate: document.getElementById('btn-simulate'),
      checkSimulateError: document.getElementById('check-simulate-error'),
      btnViewGeojson: document.getElementById('btn-view-geojson'),
      backendStatusBadge: document.getElementById('backend-status-badge'),
      
      // GeoJSON modal
      geojsonModal: document.getElementById('geojson-modal'),
      geojsonCode: document.getElementById('geojson-code'),
      btnCloseModal: document.getElementById('btn-close-modal'),
      btnCopyGeojson: document.getElementById('btn-copy-geojson'),

      // Calendar & periods
      periodsContainer: document.getElementById('periods-container'),
      btnAddPeriod: document.getElementById('btn-add-period'),

      // Crop catalog
      cropCatalogContainer: document.getElementById('crop-catalog-container'),

      // Simulation modes
      priorityButtons: document.querySelectorAll('.priority-btn'),

      // Indicators
      indicatorW: document.getElementById('ind-humedad-w'),
      indicatorT: document.getElementById('ind-temp-t'),
      indicatorNPK: document.getElementById('ind-npk'),
      indicatorH: document.getElementById('ind-espesor-h'),
      indicatorShield: document.getElementById('ind-escudo'),

      // What-If physical model sliders
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

      // Liebig chemical health
      valLiebigPct: document.getElementById('val-liebig-pct'),
      liebigBarFill: document.getElementById('liebig-bar-fill'),
      liebigLimitingBadge: document.getElementById('liebig-limiting-badge'),
      pillNpkN: document.getElementById('pill-npk-n'),
      pillNpkP: document.getElementById('pill-npk-p'),
      pillNpkK: document.getElementById('pill-npk-k'),

      // Irrigation alerts
      irrigationAlertCard: document.getElementById('irrigation-alert-card'),
      badgeIrrigationStatus: document.getElementById('badge-irrigation-status'),
      valWcrit: document.getElementById('val-wcrit'),
      valTauAviso: document.getElementById('val-tau-aviso'),
      valIsugerido: document.getElementById('val-isugerido'),
      btnApplyIrrigationSuggested: document.getElementById('btn-apply-irrigation-suggested'),

      // Monte Carlo confidence and shield states
      valMontecarloConf: document.getElementById('val-montecarlo-conf'),
      pillAzul: document.getElementById('pill-azul'),
      pillVioleta: document.getElementById('pill-violeta'),
      pillRojo: document.getElementById('pill-rojo'),
      pillDesactivado: document.getElementById('pill-desactivado'),

      // Rotation
      rotationTableBody: document.getElementById('rotation-table-body'),
      rotationReason: document.getElementById('rotation-reason'),
      btnApplySuggestion: document.getElementById('btn-apply-suggestion'),

      // Notifications and alerts
      toastContainer: document.getElementById('toast-container'),
      locationInfo: document.getElementById('location-info'),
      btnLocateMe: document.getElementById('btn-locate-me'),
      btnLayerToggle: document.getElementById('btn-layer-toggle')
    };
  }

  bindEvents() {
    // 1. Step navigation
    this.elements.stepTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const step = parseInt(tab.dataset.step, 10);
        this.goToStep(step);
      });
    });

    // 2. Mobile view toggle (Map vs Panel)
    this.elements.viewToggleButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        this.switchMobileView(view);
      });
    });

    // 3. Lot management buttons
    if (this.elements.btnAddLote) {
      this.elements.btnAddLote.addEventListener('click', () => {
        try {
          if (this.lotesManager.getAll().length >= CONFIG.LIMITS.MAX_LOTES) {
            this.showToast(`Zone limit reached (maximum ${CONFIG.LIMITS.MAX_LOTES} zones for this release).`, "warning");
            return;
          }
          this.mapManager.startDrawPolygon();
          this.switchMobileView("map");
          this.showToast("Draw your parcel on the map by tapping field boundary points.", "info");
        } catch (e) {
          this.showToast(e.message, "error");
        }
      });
    }

    if (this.elements.btnConfirmLote) {
      this.elements.btnConfirmLote.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (!selected) {
          this.showToast("First draw or select a parcel on the map.", "warning");
          return;
        }
        this.lotesManager.confirmLote(selected.id);
        this.showToast(`Boundary of "${selected.name}" confirmed successfully!`, "success");
      });
    }

    if (this.elements.btnEditLote) {
      this.elements.btnEditLote.addEventListener('click', () => {
        this.mapManager.startEditMode();
        this.switchMobileView("map");
        this.showToast("Edit mode enabled: drag vertices to adjust the boundary.", "info");
      });
    }

    if (this.elements.btnDeleteLote) {
      this.elements.btnDeleteLote.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (!selected) return;
        if (confirm(`Are you sure you want to delete "${selected.name}"?`)) {
          this.lotesManager.removeLote(selected.id);
          this.showToast("Lot deleted.", "info");
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

    // Buttons to open the 2.5D Shield view
    const openEscudoView = () => {
      this.goToStep(4);
      this.switchMobileView("panel");
      this.showToast("🛡️ 2.5D Digital Twin: Protective shield mesh suspended over your crops.", "info");
    };

    if (this.elements.btnStep1Shield) {
      this.elements.btnStep1Shield.addEventListener('click', openEscudoView);
    }

    if (this.elements.btnMapShield) {
      this.elements.btnMapShield.addEventListener('click', openEscudoView);
    }

    // 4. Primary simulation button (with strict selection preservation on failure)
    if (this.elements.btnSimulate) {
      this.elements.btnSimulate.addEventListener('click', () => this.handleSimulation());
    }

    // Force-error checkbox to demonstrate resilience
    if (this.elements.checkSimulateError) {
      this.elements.checkSimulateError.addEventListener('change', (e) => {
        this.apiService.forceFailureForTesting = e.target.checked;
        if (e.target.checked) {
          this.showToast("Error test mode enabled: The next simulation will fail to verify your selection stays intact.", "warning");
        }
      });
    }

    // 5. GeoJSON modal
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
          this.showToast("GeoJSON copied to clipboard", "success");
        });
      });
    }

    // 6. Geolocation button
    if (this.elements.btnLocateMe) {
      this.elements.btnLocateMe.addEventListener('click', () => {
        this.showToast("Looking up your location… If prompted, select «Allow».", "info");
        this.mapManager.locateUser(
          (coords) => {
            const acc = Number.isFinite(coords?.accuracy) ? ` (±${Math.ceil(coords.accuracy)} m)` : "";
            this.showToast(`Location found on the map${acc}.`, "success");
          },
          (err) => {
            this.showToast(err?.message || "Could not acquire GPS signal; keeping view on Mantaro Valley.", "warning", 6000);
          }
        );
      });
    }

    // 7. Toggle satellite imagery layer
    if (this.elements.btnLayerToggle) {
      this.elements.btnLayerToggle.addEventListener('click', () => {
        const nextLayer = this.mapManager.activeBaseLayer === "esriSatellite" ? "osm" : "esriSatellite";
        this.mapManager.toggleBaseLayer(nextLayer);
        this.elements.btnLayerToggle.textContent = nextLayer === "esriSatellite" ? "🛰️ Satellite" : "🗺️ Street Map";
      });
    }

    // 8. Priority modes
    this.elements.priorityButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        this.elements.priorityButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.activePriorityMode = btn.dataset.mode;
        this.showToast(`Mode switched to: ${btn.textContent.trim()}`, "info");
        // Reuse existing simulation without re-running per milestone CC-08
        if (this.apiService.lastSimulationResult) {
          this.renderSimulationResults(this.apiService.lastSimulationResult);
        }
      });
    });

    // 9. Apply suggested rotation
    if (this.elements.btnApplySuggestion) {
      this.elements.btnApplySuggestion.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (selected) {
          selected.cultivo_asignado = "habas_verdes";
          this.lotesManager.updateLote(selected.id, { cultivo_asignado: "habas_verdes" });
          this.showToast("Suggested rotation applied to your parcel!", "success");
          this.goToStep(3); // Go view crops
        }
      });
    }

    // 10. Add period
    if (this.elements.btnAddPeriod) {
      this.elements.btnAddPeriod.addEventListener('click', () => {
        const selected = this.lotesManager.getSelected();
        if (!selected) return;
        const newPIndex = selected.periodos.length + 1;
        selected.periodos.push({
          id: `P${newPIndex}`,
          name: `Season ${newPIndex}`,
          start: "Oct",
          end: "Dec",
          cropId: "avena_forrajera"
        });
        this.lotesManager.updateLote(selected.id, { periodos: selected.periodos });
        this.renderPeriods();
        this.showToast(`Period P${newPIndex} added to the calendar.`, "success");
      });
    }
  }

  /**
   * Configure map place search (/api/places)
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
        status.textContent = "Enter at least two characters.";
        return;
      }

      button.disabled = true;
      results.replaceChildren();
      results.hidden = true;
      status.textContent = "Searching places…";

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
          ? "Choose a place to center the map."
          : "No places found. Try adding the region or country.";
      } catch {
        status.textContent = "Place search is currently unavailable. You can pan the map manually.";
      } finally {
        button.disabled = false;
      }
    });
  }

  /**
   * Bind event listeners on What-If control sliders
   * with dynamic Auto-Balance support across coupled variables
   */
  setupWhatIfControls() {
    const el = this.elements;

    // Auto-balance checkbox
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
            ? "⚖️ Auto-Balance ENABLED: Knobs will compensate each other automatically."
            : "Manual mode: Independent adjustment per knob.",
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

    // Regime selector (Active Crop vs Bare Soil)
    if (el.btnStageCrop && el.btnStageTrans) {
      el.btnStageCrop.addEventListener('click', () => {
        this.whatIfControls.stage = "cultivo";
        el.btnStageCrop.classList.add('active');
        el.btnStageTrans.classList.remove('active');
        if (el.valStageText) el.valStageText.textContent = "Active Crop";
        if (el.visorStageTag) el.visorStageTag.textContent = "Active Crop";
        this.recalculatePhysicalModel();
      });

      el.btnStageTrans.addEventListener('click', () => {
        this.whatIfControls.stage = "transicion";
        el.btnStageTrans.classList.add('active');
        el.btnStageCrop.classList.remove('active');
        if (el.valStageText) el.valStageText.textContent = "Bare Soil (Transition)";
        if (el.visorStageTag) el.visorStageTag.textContent = "q = Transition";
        this.recalculatePhysicalModel();
      });
    }

    // Apply suggested irrigation button
    if (el.btnApplyIrrigationSuggested) {
      el.btnApplyIrrigationSuggested.addEventListener('click', () => {
        const suggested = this.lastSuggestedIrrigation || 25;
        if (el.sliderIrrigation) {
          el.sliderIrrigation.value = suggested;
          this.whatIfControls.irrigationI = suggested;
          if (el.valIrrigation) el.valIrrigation.textContent = `${suggested} mm`;
          this.recalculatePhysicalModel();
          this.showToast(`💧 Suggested irrigation depth of ${suggested} mm applied to the scenario.`, "success");
        }
      });
    }

    // Quick-demo clicks on the 4 shield state pills
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
        this.showToast("State activated: 🔵 Cobalt Blue (Optimal Resilience, Ψ > 0.70)", "info");
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
        this.showToast("State activated: 🟣 Violet / Amber (Moderate Stress, Ψ ≈ 0.50)", "warning");
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
        this.showToast("State activated: 🔴 Deep Red (Critical Stress / Collapse, Ψ < 0.38)", "error");
      });
    }

    if (el.pillDesactivado) {
      el.pillDesactivado.addEventListener('click', () => {
        this.whatIfControls.stage = "transicion";
        this.syncSliderInputs();
        this.recalculatePhysicalModel();
        this.showToast("State activated: ⚪ Shield Deactivated (q = Transition, bare soil)", "info");
      });
    }
  }

  // Compensate with management without changing the chosen climate or slope.
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
      if (el.valStageText) el.valStageText.textContent = "Active Crop";
    } else {
      el.btnStageTrans?.classList.add('active');
      el.btnStageCrop?.classList.remove('active');
      if (el.valStageText) el.valStageText.textContent = "Bare Soil (Transition)";
    }
  }

  /**
   * Recalculate the dynamic physical model and sync UI and 2.5D viewer
   */
  recalculatePhysicalModel() {
    const el = this.elements;
    const phys = this.physicsEngine.evaluate(this.whatIfControls);

    if (this.mapManager.terrain) {
      this.mapManager.terrain.controls = { ...this.whatIfControls };
      this.mapManager.terrain.physics = phys;
      // Debounce rapid slider events into a single redraw.
      clearTimeout(this.terrainRedrawTimer);
      this.terrainRedrawTimer = setTimeout(() => this.mapManager.gridLayer?.redraw(), 80);
    }

    // 1. Update 2.5D Square Hills + Flat Shield viewer
    if (this.escudo3d) {
      this.escudo3d.updatePhysicsState(phys);
    }

    // 2. Erosion and soil subsidence info
    if (el.lblErosionRate) el.lblErosionRate.textContent = `${phys.erosionRateMmYear} mm/year`;
    if (el.txtSinkingInfo) el.txtSinkingInfo.innerHTML = `Erosion subsidence: <strong>${phys.erosionSinkingMm} mm</strong>`;

    // 3. Liebig's Law chemical health
    if (el.valLiebigPct) el.valLiebigPct.textContent = `${Math.round(phys.eta_nutrientes * 100)}%`;
    if (el.liebigBarFill) {
      el.liebigBarFill.style.width = `${Math.round(phys.eta_nutrientes * 100)}%`;
      el.liebigBarFill.style.boxShadow = `0 0 12px ${phys.eta_nutrientes > 0.65 ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)'}`;
    }

    if (el.liebigLimitingBadge) {
      el.liebigLimitingBadge.innerHTML = `<span>⚠️ Growth limited by <strong>${phys.limitingNutrient}</strong> per Liebig's Law</span>`;
    }

    // Update NPK pills
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

    // 4. Irrigation alerts
    this.lastSuggestedIrrigation = phys.irrigationAlert.Isugerido;
    if (el.valWcrit) el.valWcrit.textContent = `${phys.irrigationAlert.W_crit} mm`;
    if (el.valTauAviso) el.valTauAviso.textContent = `${phys.irrigationAlert.tauAviso} days`;
    if (el.valIsugerido) el.valIsugerido.textContent = `${phys.irrigationAlert.Isugerido} mm`;

    if (el.irrigationAlertCard) {
      el.irrigationAlertCard.classList.toggle('alert-active', phys.irrigationAlert.active);
    }
    if (el.badgeIrrigationStatus) {
      if (phys.irrigationAlert.active) {
        el.badgeIrrigationStatus.textContent = "⚠️ Imminent Water Stress";
        el.badgeIrrigationStatus.className = "gap-badge gap-gap";
      } else {
        el.badgeIrrigationStatus.textContent = "Adequate Moisture";
        el.badgeIrrigationStatus.className = "gap-badge gap-obs";
      }
    }

    // 5. Monte Carlo confidence
    if (el.valMontecarloConf) el.valMontecarloConf.textContent = `${phys.montecarloConfidence}%`;

    // 6. Sync 4 Shield State pills
    const s = phys.shieldState;
    el.pillAzul?.classList.toggle('active-azul', s === 'azul_cobalto');
    el.pillVioleta?.classList.toggle('active-violeta', s === 'violeta_ambar');
    el.pillRojo?.classList.toggle('active-rojo', s === 'rojo_intenso');
    el.pillDesactivado?.classList.toggle('active-desactivado', s === 'desactivado');

    // 7. Update scalar indicators
    if (el.indicatorW) {
      el.indicatorW.innerHTML = `
        <div class="stat-value" style="color: ${phys.W < 95 ? '#ef4444' : '#10b981'}">${phys.W} <small>mm</small></div>
        <div class="stat-label">Root moisture (W)</div>
        <div class="stat-badge ${phys.W < 95 ? 'badge-amber' : 'badge-green'}">${phys.W < 95 ? 'Stress alert' : 'Adequate'}</div>
      `;
    }

    if (el.indicatorT) {
      el.indicatorT.innerHTML = `
        <div class="stat-value" style="color: ${phys.T > 22 || phys.T < 10 ? '#f59e0b' : '#38bdf8'}">${phys.T} <small>°C</small></div>
        <div class="stat-label">Canopy temp (T)</div>
        <div class="stat-badge ${phys.T > 22 ? 'badge-amber' : 'badge-blue'}">${phys.T > 22 ? 'Thermal stress' : 'Optimal'}</div>
      `;
    }

    if (el.indicatorH) {
      el.indicatorH.innerHTML = `
        <div class="stat-value">${phys.H} <small>mm</small></div>
        <div class="stat-label">Fertile topsoil (H)</div>
        <div class="stat-badge ${phys.erosionRateMmYear > 2 ? 'badge-amber' : 'badge-green'}">${phys.erosionRateMmYear} mm/year</div>
      `;
    }

    if (el.indicatorNPK) {
      el.indicatorNPK.innerHTML = `
        <div class="stat-value">N:${this.whatIfControls.fertN} P:${this.whatIfControls.fertP} K:${this.whatIfControls.fertK}</div>
        <div class="stat-label">NPK Dose kg/ha</div>
        <div class="stat-badge badge-amber">${phys.limitingNutrient}</div>
      `;
    }
  }

  /**
   * Run simulation with strict preservation of active parcel selection
   */
  async handleSimulation() {
    const selected = this.lotesManager.getSelected();
    if (!selected) {
      this.showToast("Select or draw a parcel first.", "warning");
      this.goToStep(1);
      return;
    }

    // 1. Mark status "confirmed" if still draft
    this.lotesManager.confirmLote(selected.id);

    // 2. Build GeoJSON payload for the server
    const payload = this.lotesManager.toSimulationPayload({
      mode: this.activePriorityMode
    });

    // 3. Put UI in loading state
    this.elements.btnSimulate.disabled = true;
    this.elements.btnSimulate.innerHTML = `<span class="spinner"></span> Simulating terrain response...`;

    const selectedIdBefore = selected.id;

    try {
      this.showToast("Sending GeoJSON coordinates to the server...", "info");
      
      // Call API (with offline fallback option if server is unreachable)
      const results = await this.apiService.runSimulation(payload, {
        useOfflineFallback: true
      });

      // Verify active selection is preserved
      this.lotesManager.select(selectedIdBefore);

      // Display results
      this.renderSimulationResults(results);

      if (results._is_fallback) {
        this.showToast("⚠️ Backend server unavailable. Using fallback physical data (NASA POWER Mantaro). Your parcel remains selected.", "warning", 6000);
      } else {
        this.showToast("✅ Simulation completed successfully.", "success");
      }

      // Advance to Step 4 (Diagnostics) to inspect results
      this.goToStep(4);

    } catch (err) {
      console.error("Simulation error:", err);

      // CRITICAL REQUIREMENT: PRESERVE SELECTION WHEN SIMULATION FAILS
      // Guarantee the lot stays selected both in state and on the map
      if (selectedIdBefore) {
        this.lotesManager.select(selectedIdBefore);
      }

      const isTest = err.isSimulatedTest;
      const errorTitle = isTest 
        ? "⚠️ Resilience Test: The simulation failed intentionally." 
        : "⚠️ Could not complete the simulation on the server.";
      
      const errorMessage = `${errorTitle} Your parcel "${selected.name}" and its GeoJSON coordinates were kept selected and intact on your device.`;

      this.showToast(errorMessage, "error", 7000);
      this.showPersistentErrorBanner(selected, err.message);

    } finally {
      this.elements.btnSimulate.disabled = false;
      this.elements.btnSimulate.innerHTML = `<span>🚀 Simulate Terrain</span>`;
      // Re-verify selection state
      this.updateLoteStats(this.lotesManager.getSelected());
    }
  }

  /**
   * Persistent alert banner when a simulation failure occurs
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
          <strong>Selection Protected:</strong> The simulation failed (${reason}), but <strong>${lote.name}</strong> (${lote.area_ha} ha) remains selected and no vertices were lost.
        </div>
        <button class="banner-close" onclick="this.parentElement.parentElement.remove()">✕</button>
      </div>
    `;

    document.querySelector('.app-main').prepend(banner);
  }

  /**
   * Render simulation results into the diagnostic indicators
   */
  renderSimulationResults(data) {
    if (!data || !data.indicadores) return;

    const ind = data.indicadores;

    // Update the 2.5D Shield visual model
    if (this.escudo3d) {
      this.escudo3d.updateMetrics({
        humedad_W: ind.humedad_radicular_W?.valor,
        temperatura_T: ind.temperatura_dosel_T?.valor,
        espesor_H: ind.espesor_fertil_H?.valor,
        escudoScore: ind.escudo_ambiental?.indice,
        biomasa_B: ind.biomasa_aerea_B?.valor
      });
    }

    // Root-zone moisture W
    if (this.elements.indicatorW) {
      this.elements.indicatorW.innerHTML = `
        <div class="stat-value" style="color: ${ind.humedad_radicular_W.color}">${ind.humedad_radicular_W.valor} <small>${ind.humedad_radicular_W.unidad}</small></div>
        <div class="stat-label">Root moisture (W)</div>
        <div class="stat-badge badge-green">${ind.humedad_radicular_W.estado}</div>
      `;
    }

    // Canopy temperature T
    if (this.elements.indicatorT) {
      this.elements.indicatorT.innerHTML = `
        <div class="stat-value" style="color: ${ind.temperatura_dosel_T.color}">${ind.temperatura_dosel_T.valor} <small>${ind.temperatura_dosel_T.unidad}</small></div>
        <div class="stat-label">Canopy temp (T)</div>
        <div class="stat-badge badge-blue">${ind.temperatura_dosel_T.estado}</div>
      `;
    }

    // NPK nutrients
    if (this.elements.indicatorNPK) {
      const npk = ind.nutrientes_NPK;
      this.elements.indicatorNPK.innerHTML = `
        <div class="stat-value">N:${npk.N.valor} P:${npk.P.valor} K:${npk.K.valor}</div>
        <div class="stat-label">Nutrients kg/ha</div>
        <div class="stat-badge badge-amber">${npk.estado_general}</div>
      `;
    }

    // Fertile topsoil H
    if (this.elements.indicatorH) {
      this.elements.indicatorH.innerHTML = `
        <div class="stat-value">${ind.espesor_fertil_H.valor} <small>${ind.espesor_fertil_H.unidad}</small></div>
        <div class="stat-label">Fertile topsoil (H)</div>
        <div class="stat-badge badge-green">${ind.espesor_fertil_H.tasa_erosion}</div>
      `;
    }

    // Environmental shield
    if (this.elements.indicatorShield) {
      const shield = ind.escudo_ambiental;
      this.elements.indicatorShield.innerHTML = `
        <div class="stat-value" style="color: ${shield.color}">${shield.indice} <small>/ ${shield.max}</small></div>
        <div class="stat-label">Environmental Shield</div>
        <div class="stat-badge badge-green">${shield.calificacion}</div>
      `;
    }

    // Rotation comparison table
    if (data.rotacion_recomendada && this.elements.rotationTableBody) {
      const rot = data.rotacion_recomendada;
      this.elements.rotationTableBody.innerHTML = rot.sugerencia_optimizada.map(item => `
        <tr>
          <td><strong>${item.periodo}</strong></td>
          <td><span class="crop-pill">${item.cultivo}</span></td>
          <td><small class="text-green">${item.ventaja || item.rendimiento_est || 'Base plan'}</small></td>
        </tr>
      `).join('');

      if (this.elements.rotationReason) {
        this.elements.rotationReason.textContent = rot.motivo_agronomico;
      }
    }
  }

  /**
   * Render initial crop catalog
   */
  renderCropCatalog() {
    if (!this.elements.cropCatalogContainer) return;

    this.elements.cropCatalogContainer.innerHTML = CONFIG.CROP_CATALOG.map(crop => `
      <div class="crop-card" data-crop-id="${crop.id}">
        <div class="crop-icon">${crop.icon}</div>
        <div class="crop-info">
          <div class="crop-name">${crop.name}</div>
          <div class="crop-meta">${crop.family} &bull; ${crop.cycle_days} days</div>
          <div class="crop-impact">${crop.soil_impact}</div>
        </div>
        <button class="btn-select-crop" title="Assign to period">Assign</button>
      </div>
    `).join('');

    // Crop selection events
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
      this.showToast("Select a lot first.", "warning");
      return;
    }

    const crop = CONFIG.CROP_CATALOG.find(c => c.id === cropId);
    if (!crop) return;

    // Update the active period
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
    this.showToast(`"${crop.name}" assigned to ${this.activePeriod} of ${selectedLote.name}`, "success");
  }

  /**
   * Render the calendar with readable month ticks
   * "one tick per month, with labels like Jan · Feb · Mar"
   */
  renderPeriods() {
    if (!this.elements.periodsContainer) return;

    const selected = this.lotesManager.getSelected();
    const periods = selected ? selected.periodos : [
      { id: "P1", name: "Short Season", start: "Jan", end: "May", cropId: "papa_canchan" },
      { id: "P2", name: "Main Season", start: "Jun", end: "Dec", cropId: "habas_verdes" }
    ];

    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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

    // Period click handlers
    this.elements.periodsContainer.querySelectorAll('.period-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        this.activePeriod = chip.dataset.periodId;
        this.renderPeriods();
        this.showToast(`Active period: ${this.activePeriod}. Pick a crop to assign it.`, "info");
      });
    });
  }

  /**
   * Subscribe to lot manager updates
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
    status.textContent = selected ? 'Computing canopy temperature from NASA POWER & SRTM…' : '';
    if (!selected) return;

    const request = new AbortController();
    this.parcelEdo1Request = request;
    this.parcelEdo1Timer = setTimeout(async () => {
      try {
        const result = await this.apiService.runParcelEdo1(selected, request.signal);
        if (request.signal.aborted) return;
        this.mapManager.showParcelTemperatures(result.cells);
        const crop = result.reference_crop_used ? `${result.crop} (reference crop)` : result.crop;
        status.textContent = `ODE 1 · ${result.cells_count} 30 m cells · Mean canopy ${result.lot_mean_temp} °C · ${result.date} (local solar time) · ${crop} · Assumed root water: ${result.soil_water_mm} mm`;
      } catch (error) {
        if (request.signal.aborted) return;
        status.textContent = `ODE 1: ${error.name === 'TimeoutError' ? 'The request took too long.' : error.message}`;
        retryButton.hidden = false;
      }
    }, 350);
  }

  renderLotesList(lotes, selected) {
    if (!this.elements.lotesList) return;

    if (lotes.length === 0) {
      this.elements.lotesList.innerHTML = `
        <div class="empty-state">
          <p>No lots drawn yet.</p>
          <small>Tap "+ Draw Lot" to trace your parcel with Geoman.</small>
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
              ${isConfirmed ? 'Confirmed' : 'Draft'}
            </span>
          </div>
          <div class="lote-card-bottom">
            <span><strong>${lote.area_ha}</strong> ha (${lote.area_m2.toLocaleString()} m²)</span>
            <button class="btn-micro-select" title="Select">${isSelected ? 'Active' : 'Select'}</button>
          </div>
        </div>
      `;
    }).join('');

    // Lot selection click handler
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
      if (this.elements.statLoteName) this.elements.statLoteName.textContent = "No lot selected";
      if (this.elements.statLoteAreaHa) this.elements.statLoteAreaHa.textContent = "0.00 ha";
      if (this.elements.statLoteAreaM2) this.elements.statLoteAreaM2.textContent = "0 m²";
      if (this.elements.statLotePerimeter) this.elements.statLotePerimeter.textContent = "0 m";
      if (this.elements.statLoteStatusBadge) {
        this.elements.statLoteStatusBadge.textContent = "No parcel";
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
      this.elements.statLoteStatusBadge.textContent = isConfirmed ? "Confirmed" : "Draft (Unconfirmed)";
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

    // On mobile screens, show the map in Step 1 and the panel in other steps
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
        // Invalidate map size when becoming visible again
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
        this.elements.backendStatusBadge.innerHTML = `<span class="dot-online"></span> Backend Connected`;
        this.elements.backendStatusBadge.className = "badge-server badge-online";
      } else {
        this.elements.backendStatusBadge.innerHTML = `<span class="dot-offline"></span> Backup / Offline Mode`;
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
