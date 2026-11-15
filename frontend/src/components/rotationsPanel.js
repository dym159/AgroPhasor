import { fetchRotation, parcelToGeoJsonGeometry } from '../services/agroApi.js';
import { createElement as el } from '../utils/dom.js';
import { formatPhaseDate } from '../utils/phaseDates.js';
import { VISUAL_CROPS } from '../data/mockVisualData.js';
import { createRotationState, economyAvailable, ROUTE_NAMES } from '../state/rotationState.js';

const text = (tag, value) => el(tag, {text:value});
const label = (name, input) => el('label', {}, [text('span',name),input]);
const names = Object.fromEntries(VISUAL_CROPS.map(c => [c.id,c.name]));
const cropName = id => names[id] ?? id;
const plan = (stages, calendar = false) => el('ol',{}, stages.map(s => el('li',{},[
  text('strong',cropName(calendar ? s.cropId : s.crop_id)),
  text('span',`${formatPhaseDate(s.start)} → ${s.harvest ? formatPhaseDate(s.harvest) : 'Sin fecha de cosecha'}`),
])));

export function createRotationsPanel(container, onApply) {
  if (!container) return {update() {}};
  let state, signature = '', requested = false, applying = false, testedCount, lastRequest = '';
  const fields = {}, fixedChecks = new Map();
  function number(key,title,max,integer = false) {
    const input = el('input',{type:'number',attrs:{min:0,step:integer ? 1 : 'any',required:'',
      ...(max == null ? {} : {max}), 'aria-label':title}});
    fields[key] = input;
    return label(title,input);
  }
  const scenario = el('textarea',{attrs:{rows:4,'aria-label':'Escenarios climáticos JSON',
    placeholder:'Vacío: NASA POWER. Opcional: lista JSON de escenarios {id, daily}'}});
  const form = el('form',{className:'rotation-form'},[
    text('p','Completa los datos iniciales; no se rellenan con valores de ejemplo.'),
    el('details',{attrs:{open:''}},[text('summary','Suelo inicial y manejo'),
      number('W','Agua inicial (mm)'),number('N','Nitrógeno (kg/ha)'),
      number('P','Fósforo (kg/ha)'),number('K','Potasio (kg/ha)'),
      number('H','Espesor fértil (mm)'),number('residue','Rastrojo inicial (t/ha)'),
      number('OM','Materia orgánica (%)',100),
      number('transition_days','Preparación entre cultivos (días)',365,true),
      number('residue_percent','Rastrojo que conservarás (%)',100),
      number('slope_deg','Pendiente de la columna de suelo (grados)',80),
      number('irrigation_mm_day','Riego diario (mm)',30),
      number('irrigation_cost_usd_mm_ha','Costo del riego (USD/mm/ha)'),
      text('p','La API evalúa una columna de suelo; no integra la variación de toda la parcela.'),
    ]),
    el('details',{},[text('summary','Escenario climático activo'),
      text('p','Vacío: clima histórico NASA POWER. Los escenarios propios requieren una lista JSON con id y daily: MM-DD → lluvia, temperatura, humedad y radiación.'),scenario]),
  ]);
  const fixed = el('fieldset');
  const economicInputs = new Map();
  const economics = el('details',{},[text('summary','Precios y costos opcionales (USD)'),
    text('p','Para comparar ganancias, completa precio y costo de todos los cultivos disponibles. No se convierten monedas ni se usan precios de ejemplo.')]);
  const status = el('p',{attrs:{role:'status','aria-live':'polite'}});
  const controls = el('section',{className:'rotation-controls'});
  const result = el('section',{className:'rotation-comparison'});
  const submit = el('button',{type:'submit',className:'btn',text:'Ver rotaciones sugeridas'});
  const undo = el('button',{type:'button',className:'btn',text:'Deshacer',onClick:() => {
    applying = true; model.undo(onApply); applying = false;
  }});
  form.append(economics,fixed,submit);
  container.replaceChildren(text('h2','Rotaciones sugeridas'),form,status,controls,result,undo);
  container.classList.add('rotation-workflow');
  const model = createRotationState(fetchRotation, render);

  function payload() {
    if (!state?.selectedParcel) throw new Error('Selecciona o dibuja una parcela.');
    if (state.phases.length < 2 || state.phases.length > 6 || state.phases.some(p => !p.cropId || !p.harvest))
      throw new Error('Crea entre dos y seis periodos con cultivo y cosecha en el calendario.');
    if (!form.reportValidity()) throw new Error('Completa los datos de suelo y manejo.');
    const value = key => fields[key].valueAsNumber;
    const p = {
      geometry:parcelToGeoJsonGeometry(state.selectedParcel),
      periods:state.phases.map(p => ({start:p.start})), m:state.phases.length,
      crop_ids:Object.keys(state.cropCycles).filter(id => names[id]),
      fixed:Object.fromEntries([...fixedChecks].filter(([,c]) => c.checked).map(([i]) => [i,state.phases[i].cropId])),
      initial_state:Object.fromEntries(['W','N','P','K','H','residue','OM'].map(k => [k,value(k)])),
      transition_days:value('transition_days'),residue_fraction:value('residue_percent')/100,
      slope_deg:value('slope_deg'),irrigation_mm_day:value('irrigation_mm_day'),
      irrigation_cost_usd_mm_ha:value('irrigation_cost_usd_mm_ha'),
      prices_usd_t:Object.fromEntries([...economicInputs].filter(([,v]) => v.price.value !== '').map(([id,v]) => [id,v.price.valueAsNumber])),
      costs_usd_ha:Object.fromEntries([...economicInputs].filter(([,v]) => v.cost.value !== '').map(([id,v]) => [id,v.cost.valueAsNumber])),
    };
    if (!p.geometry) throw new Error('La parcela necesita un polígono válido.');
    if (!p.crop_ids.length) throw new Error('Espera a que se cargue el catálogo de cultivos.');
    if (scenario.value.trim()) {
      try { p.scenarios = JSON.parse(scenario.value); }
      catch { throw new Error('Escenarios: revisa el formato JSON.'); }
      if (!Array.isArray(p.scenarios) || !p.scenarios.length) throw new Error('Introduce una lista no vacía de escenarios.');
    }
    return p;
  }
  async function calculate() {
    try {
      const p = payload(), key = JSON.stringify(p);
      if (key === lastRequest && ['loading','ready','empty'].includes(model.snapshot().status)) return;
      lastRequest = key; testedCount = p.scenarios?.length; requested = true; await model.load(p);
    }
    catch (error) { model.invalidate(); status.textContent = error.message; }
  }
  form.addEventListener('submit',event => {event.preventDefault(); calculate();});
  form.addEventListener('change',() => {if (requested) calculate();});

  function render(snapshot) {
    const {data,selected,weights,route} = snapshot;
    submit.disabled = snapshot.status === 'loading'; undo.hidden = !snapshot.canUndo;
    controls.replaceChildren(); result.replaceChildren();
    status.textContent = {idle:'Completa el suelo y solicita las sugerencias.',loading:'Calculando rotaciones…',
      error:snapshot.error,empty:'Sin rotaciones viables.',ready:'Estimación · Menos es mejor en las cuatro notas.'}[snapshot.status];
    if (!data) return;
    result.append(el('aside',{className:'rotation-notices',attrs:{'aria-label':'Avisos del modelo'}},
      (data.avisos ?? []).map(note => text('p',note))));
    if (!selected) {
      result.append(...(data.reasons ?? []).map(r => text('p',`${r.sequence?.map(cropName).join(' → ') ?? ''}: ${r.reason}`)));
      return;
    }
    const economic = economyAvailable(data.pareto);
    const group = route.startsWith('A') ? 'A' : route.startsWith('C') ? 'C' : 'B';
    controls.append(el('div',{className:'rotation-modes'},[
      ...[['A','Máxima Resiliencia'],['B','Balance Óptimo'],['C','Mayor Ganancia']].map(([prefix,title]) =>
        el('button',{type:'button',text:title,attrs:{'aria-pressed':String(group === prefix)},
          onClick:() => model.choose(Object.keys(ROUTE_NAMES).find(n => n.startsWith(prefix)))})),
    ]));
    for (const [key,title] of Object.entries(ROUTE_NAMES).filter(([k]) => k.startsWith(group))) {
      const button = el('button',{type:'button',text:title,attrs:{'aria-pressed':String(route === key)},onClick:() => model.choose(key)});
      button.disabled = !data.recomendada_por_ruta[key] || (!economic && ['C2_mayor_ganancia','C3_equilibrio_rapidez_ganancia'].includes(key));
      controls.append(button);
    }
    if (!economic) controls.append(text('p','Faltan precios o costos. Ganar más, Rápido y rentable y el control de ganancia están desactivados.'));
    const sliders = el('details',{},[text('summary','Ajustar lo que más te importa')]);
    ['Gastar menos agua','Dejar mejor la tierra','Ganar más','Cobrar más rápido'].forEach((title,i) => {
      const input = el('input',{type:'range',attrs:{min:0,max:100,step:1,value:weights[i]*100,'aria-label':title}});
      input.disabled = i === 2 && !economic;
      input.addEventListener('input',() => {
        const open = sliders.open; model.move(i,input.valueAsNumber/100);
        const details = controls.querySelector('details'); if (details) details.open = open;
        controls.querySelectorAll('input[type=range]')[i]?.focus();
      });
      sliders.append(label(`${title}: ${Math.round(weights[i]*100)} %`,input));
    });
    controls.append(sliders);
    const same = Object.entries(data.recomendada_por_ruta).filter(([key,v]) => key !== route && v?.id === selected.id)
      .map(([key]) => ROUTE_NAMES[key]);
    if (same.length) result.append(text('p',`Es la misma que en ${same.join(', ')}.`));
    result.append(text('h3','Tu plan actual'),plan(state.phases,true),
      text('p','Comparación numérica no disponible: este endpoint no devuelve la simulación del plan actual.'),
      text('h3','Rotación sugerida · Estimación'),plan(selected.stages));
    ['Agua y estrés: menos estrés ambiental.','Tierra: menos deterioro del suelo.',
      'Ganancia: mejor margen anual estimado.','Rapidez: ciclos más cortos.'].forEach((description,i) => {
      const value = selected.f_hat[i];
      const row = el('div',{className:'rotation-note'},[text('p',`Menos es mejor · ${description}`)]);
      if (value == null) row.append(text('span','Sin datos comparables'));
      else row.append(el('meter',{attrs:{min:0,max:1,value,'aria-label':description}}),text('span',`${Math.round(value*100)} / 100`));
      result.append(row);
    });
    const frequency = selected.survival_frequency;
    if (Number.isFinite(frequency)) result.append(text('p',testedCount && Number.isInteger(frequency*testedCount)
      ? `Sobrevive en ${frequency*testedCount} de ${testedCount} escenarios probados.`
      : `Frecuencia de supervivencia dentro de los escenarios probados: ${(frequency*100).toFixed(1)} %. La API no informa el total probado.`));
    result.append(text('p',data.motivo ?? ''),el('details',{},[
      text('summary','Origen de los datos'),
      ...Object.entries(data.origins ?? {}).map(([key,value]) => text('p',`${key}: ${value}`)),
      text('p','Observado: dato aportado o medido. Estimado: cálculo del motor. Respaldo: referencia que requiere validación local.'),
    ]),el('button',{type:'button',className:'btn',text:'Aplicar esta rotación',onClick:() => {
      applying = true;
      model.apply(state.phases,phases => onApply(phases.map(p => ({...p,
        residue_fraction:fields.residue_percent.valueAsNumber/100,
        irrigation_mm_day:fields.irrigation_mm_day.valueAsNumber}))));
      applying = false;
    }}));
  }

  return {update(next) {
    state = next;
    for (const id of Object.keys(state.cropCycles).filter(id => names[id])) {
      if (economicInputs.has(id)) continue;
      const price = el('input',{type:'number',attrs:{min:0,step:'any'}});
      const cost = el('input',{type:'number',attrs:{min:0,step:'any'}});
      economicInputs.set(id,{price,cost});
      economics.append(label(`${cropName(id)}: precio (USD/t)`,price),label(`${cropName(id)}: costo (USD/ha)`,cost));
    }
    const current = JSON.stringify([state.selectedParcel?.id,state.selectedParcel?.polygon,state.phases]);
    if (current !== signature) {
      signature = current;
      const checked = new Set([...fixedChecks].filter(([,c]) => c.checked).map(([i]) => i));
      fixedChecks.clear(); fixed.replaceChildren(text('legend','Cultivos que deseas mantener'));
      state.phases.forEach((phase,i) => {
        const input = el('input',{type:'checkbox'}); input.checked = checked.has(i); fixedChecks.set(i,input);
        fixed.append(label(`Mantener periodo ${i+1}: ${cropName(phase.cropId)}`,input));
      });
      if (!applying) model.invalidate();
    }
  }};
}
