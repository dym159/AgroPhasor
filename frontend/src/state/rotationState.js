// Selección local: los pesos de presets proceden exclusivamente de la API.
export const ROUTE_NAMES = {
  A1_menor_agua: 'Gastar menos agua', A2_mejor_suelo: 'Dejar mejor la tierra',
  A3_equilibrio_agua_suelo: 'Equilibrio agua y tierra', B_balance: 'Equilibrio total',
  C1_ganancia_rapida: 'Cobrar más rápido', C2_mayor_ganancia: 'Ganar más',
  C3_equilibrio_rapidez_ganancia: 'Rápido y rentable',
};

export function economyAvailable(front) {
  return front.length > 0 && front.every(c => Number.isFinite(c.f_hat?.[2]));
}

export function rescaleWeights(weights, index, value, active = [true,true,true,true]) {
  if (!active[index] || !Number.isFinite(value) || value < 0 || value > 1) throw new Error('Peso inválido.');
  const others = active.map((a,i) => a && i !== index ? i : -1).filter(i => i >= 0);
  const total = others.reduce((sum,i) => sum + weights[i], 0);
  return weights.map((w,i) => !active[i] ? 0 : i === index ? value
    : total > 0 ? w * (1-value)/total : (1-value)/others.length);
}

export function selectRotation(front, weights) {
  let best = null, bestScore = Infinity;
  for (const candidate of front) {
    const score = candidate.f_hat.reduce((sum,v,i) => sum + (v == null ? 0 : weights[i]*v), 0);
    if (score < bestScore || (score === bestScore && candidate.id < best.id)) {
      best = candidate; bestScore = score;
    }
  }
  return best;
}

export function createRotationState(request, onChange = () => {}) {
  let data = null, weights = [], route = 'B_balance', status = 'idle', error = '', revision = 0;
  let previous = null, controller;
  const snapshot = () => ({ data, weights, route, status, error,
    selected: data ? selectRotation(data.pareto, weights) : null, canUndo: previous !== null });
  const emit = () => onChange(snapshot());
  return {
    snapshot,
    async load(payload) {
      controller?.abort(); controller = new AbortController();
      const current = ++revision;
      status = 'loading'; error = ''; data = null; emit();
      try {
        const result = await request(payload, controller.signal);
        if (current !== revision) return;
        data = result; weights = result.weights ?? []; route = 'B_balance';
        status = result.pareto.length ? 'ready' : 'empty'; emit();
      } catch (e) {
        if (current !== revision) return;
        status = 'error'; error = e.message; emit();
      }
    },
    invalidate() {
      revision++; controller?.abort(); data = null; status = 'idle'; emit();
    },
    choose(name) {
      if (!data || !data.recomendada_por_ruta[name] ||
          (!economyAvailable(data.pareto) && name.startsWith('C') && name !== 'C1_ganancia_rapida')) return;
      route = name; weights = [...data.recomendada_por_ruta[name].weights]; emit();
    },
    move(index, value) {
      if (status !== 'ready') return;
      weights = rescaleWeights(weights,index,value,[true,true,economyAvailable(data.pareto),true]);
      route = 'custom'; emit();
    },
    apply(phases, callback) {
      const selected = snapshot().selected;
      if (!selected || status !== 'ready') return;
      previous = structuredClone(phases);
      callback(selected.stages.map(s => ({cropId:s.crop_id,start:s.start,harvest:s.harvest})));
      emit();
    },
    undo(callback) {
      if (previous === null) return;
      const plan = previous; previous = null; callback(structuredClone(plan)); emit();
    },
  };
}
