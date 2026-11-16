import test from 'node:test';
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { createRotationState, selectRotation, rescaleWeights, economyAvailable } from '../frontend/src/state/rotationState.js';
import { fetchRotation } from '../frontend/src/services/agroApi.js';
import { createRotationsPanel } from '../frontend/src/components/rotationsPanel.js';

// Valores sintéticos para probar lógica, no son resultados del modelo.
const vectors = [[.60,.30,.50,.55],[.55,.55,.35,.60],[.75,.35,.20,.40],[.70,.60,.15,.45],
  [.50,.10,.45,.60],[.65,.15,.10,.35],[.30,.05,.60,.80],[.55,.50,.45,.70],[.60,.55,.20,.40],[.25,.20,.65,.85]];
const front = [1,2,5,6,7,9,10].map(id => ({id:String(id),f:vectors[id-1],f_hat:vectors[id-1],
  stages:[{crop_id:'papa',start:'2026-01-01',harvest:'2026-04-01'}]}));
const presets = [[.7,.1,.1,.1],[.1,.7,.1,.1],[.4,.4,.1,.1],[.25,.25,.25,.25],
  [.1,.1,.1,.7],[.1,.1,.7,.1],[.1,.1,.4,.4]];
const keys = ['A1_menor_agua','A2_mejor_suelo','A3_equilibrio_agua_suelo','B_balance',
  'C1_ganancia_rapida','C2_mayor_ganancia','C3_equilibrio_rapidez_ganancia'];
const response = () => ({pareto:structuredClone(front),weights:presets[3],avisos:['Datos de respaldo'],
  recomendada_por_ruta:Object.fromEntries(keys.map((key,i) => [key,{weights:presets[i],id:selectRotation(front,presets[i]).id}]))});

test('Selección y perillas coinciden con los vectores de referencia',() => {
  assert.deepEqual(presets.map(w => selectRotation(front,w).id),['10','7','7','6','6','6','6']);
  const weights = rescaleWeights(presets[0],2,.4);
  weights.forEach((v,i) => assert(Math.abs(v-[.466667,.066667,.4,.066667][i]) < .001));
  assert(Math.abs(weights.reduce((a,b) => a+b,0)-1) < 1e-12);
  rescaleWeights([1,0,0,0],0,.4).forEach((v,i) => assert(Math.abs(v-[.4,.2,.2,.2][i]) < 1e-12));
  const started = performance.now();
  for (let i=0;i<10000;i++) selectRotation(front,presets[0]);
  const average = (performance.now()-started)/10000;
  console.log(`Selección local promedio: ${average.toFixed(4)} ms`);
  assert(average < 1);
});

test('Modos y perillas sin red; escenario nuevo sí; aplicar y deshacer',async () => {
  let calls = 0;
  const model = createRotationState(async () => {calls++; return response();});
  await model.load({scenario:'original'});
  for (const key of keys) model.choose(key);
  model.move(2,.4);
  assert.equal(calls,1);
  const original = [{cropId:'frijol',start:'2026-01-01',harvest:'2026-03-01',manualEnd:true}];
  let calendar = structuredClone(original);
  model.apply(calendar,phases => {calendar = phases;});
  assert.equal(calendar[0].cropId,'papa');
  model.undo(phases => {calendar = phases;});
  assert.deepEqual(calendar,original);
  await model.load({scenario:'changed'});
  assert.equal(calls,2);
});

test('Carga, error, sin viables, economía ausente y respaldo',async () => {
  const statuses = [];
  const model = createRotationState(async () => {throw new Error('API no disponible');},s => statuses.push(s.status));
  await model.load({});
  assert.deepEqual(statuses,['loading','error']);
  assert.equal(model.snapshot().error,'API no disponible');
  const empty = createRotationState(async () => ({pareto:[],reasons:[{reason:'letal'}]}));
  await empty.load({}); assert.equal(empty.snapshot().status,'empty');
  assert.equal(empty.snapshot().data.reasons[0].reason,'letal');
  const data = response(); data.pareto.forEach(c => {c.f_hat[2] = null; c.f[2] = null;});
  for (const v of Object.values(data.recomendada_por_ruta)) v.weights = [.4,.4,0,.2];
  data.weights = [.4,.4,0,.2]; data.recomendada_por_ruta.C2_mayor_ganancia = null;
  const missing = createRotationState(async () => data); await missing.load({});
  assert.equal(economyAvailable(missing.snapshot().data.pareto),false);
  missing.choose('C3_equilibrio_rapidez_ganancia'); assert.equal(missing.snapshot().route,'B_balance');
  missing.move(0,.7); assert.equal(missing.snapshot().weights[2],0);
  assert.throws(() => missing.move(2,.5));
  assert(missing.snapshot().data.avisos.includes('Datos de respaldo'));
});

test('Respuestas antiguas no reemplazan el escenario nuevo',async () => {
  let resolve;
  let call = 0;
  const model = createRotationState(() => ++call === 1 ? new Promise(r => {resolve=r;}) : Promise.resolve(response()));
  const first = model.load({}); await model.load({});
  resolve({pareto:[]}); await first;
  assert.equal(model.snapshot().status,'ready');
});

test('Cliente usa contrato real y muestra error del servidor',async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url,options) => {
      assert.equal(url,'/api/v1/parcelas/rotaciones');
      assert.equal(JSON.parse(options.body).m,2);
      return {ok:true,json:async () => response()};
    };
    assert.equal((await fetchRotation({m:2})).pareto.length,7);
    globalThis.fetch = async () => ({ok:false,json:async () => ({error:'Fecha inválida'})});
    await assert.rejects(fetchRotation({}),/Fecha inválida/);
    globalThis.fetch = async () => {throw new TypeError('Failed to fetch');};
    await assert.rejects(fetchRotation({}),/No se pudo conectar con el servidor de rotaciones/);
  } finally {globalThis.fetch=original;}
});

// Doble DOM mínimo para comprobar renderizado y acciones sin navegador ni red.
class Element {
  constructor(tag) { this.tag=tag; this.children=[]; this.attrs={}; this.events={}; this.value=''; this.textContent=''; this.classList={add(){}}; }
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children=items;}
  setAttribute(key,value) {this.attrs[key]=value; if(key==='value') this.value=value;}
  addEventListener(key,callback) {this.events[key]=callback;}
  reportValidity() {return true;}
  get valueAsNumber() {return Number(this.value);}
  all() {return [this,...this.children.flatMap(c => c instanceof Element ? c.all() : [])];}
  content() {return this.textContent+this.children.map(c => c instanceof Element ? c.content() : c).join(' ');}
}

test('El panel muestra la combinación y usa las perillas y cultivos del tablero',async () => {
  const originalDocument = globalThis.document, originalFetch = globalThis.fetch;
  globalThis.document = {createElement:tag => new Element(tag),createTextNode:value => value};
  try {
    const root = new Element('section');
    const requests = [];
    let result = {
      pareto: [
        { id:'water', f_hat:[0,1,1,1], stages:[{crop_id:'frijol'},{crop_id:'maiz'}] },
        { id:'profit', f_hat:[1,0,0,0], stages:[{crop_id:'papa'},{crop_id:'fresa'}] },
      ],
    };
    globalThis.fetch = async (_url, options) => {
      requests.push(JSON.parse(options.body));
      return {ok:true, json:async () => result};
    };
    const state = {
      selectedParcel:{id:'p',polygon:[[0,0],[0,1],[1,1]]},
      plantingStart:'2026-01-01', phases:[], selectedCropIds:[],
      cropCycles:{papa:130,frijol:90,maiz:120,fresa:270},
      cropCatalog:{papa:{name:'Papa'},frijol:{name:'Frijol'},maiz:{name:'Maíz'},fresa:{name:'Fresa'}},
      knobs:{w1:100,w2:0,w3:0,w4:0},
    };
    const panel = createRotationsPanel(root);
    const settle = () => new Promise(resolve => setImmediate(resolve));
    panel.update(state);
    await settle();
    assert.equal(root.hidden,true);
    assert.equal(requests.length,0);

    state.rotationRequested = true;
    panel.update(state);
    await settle();
    assert.equal(root.hidden,false);
    assert(root.content().includes('Frijol → Maíz'));
    assert(!root.all().some(n => n.tag === 'form' || n.tag === 'input'));
    assert.equal(requests[0].profile,'reference');
    assert.equal(requests[0].start_date,'2026-01-01');
    assert.equal(requests[0].m,3);
    assert.equal(requests[0].initial_state,undefined);

    panel.update({...state,knobs:{w1:0,w2:0,w3:100,w4:0}});
    assert(root.content().includes('Papa → Fresa'));
    assert.equal(requests.length,1);

    panel.update({...state,selectedCropIds:['fresa']});
    await settle();
    assert.deepEqual(requests[1].fixed,{0:'fresa'});
    result = {pareto:[]};
    panel.update({...state,selectedCropIds:['fresa','papa']});
    await settle();
    assert.deepEqual(requests[2].crop_ids,['fresa','papa']);
    assert(root.content().includes('Sin combinación viable'));
    const count = root.all().find(n => n.tag === 'select');
    assert.deepEqual(count.children.map(n => n.value),['3','4','5','6']);
    count.value = '6';
    count.events.change();
    await settle();
    assert.equal(requests[3].m,6);

    result = {pareto:[],status:'region_required',available_regions:['Junín','Puno']};
    panel.update({...state,selectedParcel:{...state.selectedParcel,id:'unknown'}});
    await settle();
    assert(root.content().includes('Identifica el departamento'));
    const department = root.all().find(n => n.attrs['aria-label'] === 'Departamento del terreno');
    department.value = 'Puno';
    department.events.change();
    await settle();
    assert.equal(requests[5].region,'Puno');
  } finally {globalThis.document=originalDocument; globalThis.fetch=originalFetch;}
});
