/**
 * AgroPhasor - Interfaz de Usuario y Recorrido del Agricultor
 * Pasos: 1. Parcela -> 2. Calendario -> 3. Cultivos -> 4. Diagnóstico -> 5. Rotación
 */

import { CONFIG } from './config.js';

export class UIManager {
  constructor({ lotesManager, mapManager, apiService, escudo3d }) {
    this.lotesManager = lotesManager;
    this.mapManager = mapManager;
    this.apiService = apiService;
    this.escudo3d = escudo3d;

    this.activeStep = 1;
    this.activeTab = "map"; // Para móvil: "map" | "panel"
    this.activePeriod = "P1";
    this.activePriorityMode = "balance_optimo"; // "maxima_resiliencia" | "balance_optimo" | "mayor_ganancia"

    // Elementos DOM
    this.elements = {};
  }

  init() {
    this.cacheDOMElements();
    this.bindEvents();
    this.renderCropCatalog();
    this.renderPeriods();
    this.setupLotesSubscription();
    this.checkBackendStatus();

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
        this.showToast("Buscando tu ubicación...", "info");
        this.mapManager.locateUser(
          () => this.showToast("Ubicación encontrada en el mapa.", "success"),
          () => this.showToast("No se pudo obtener la señal GPS; manteniéndote en Valle del Mantaro.", "warning")
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
    });
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
