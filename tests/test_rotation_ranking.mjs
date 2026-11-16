import test from 'node:test';
import assert from 'node:assert/strict';

import { rankCandidates } from '../frontend/src/utils/rotationRanking.js';

const SAMPLE_BOUNDS = {
  environmental_risk: [0.2, 0.8],
  soil_degradation: [0.1, 0.7],
  economic_loss: [-12000, -4000],
  payback_time: [90, 150],
};

const SAMPLE_CANDIDATES = [
  {
    id: 'papa>frijol>maiz',
    metrics: {
      environmental_risk: 0.2,
      soil_degradation: 0.5,
      economic_loss: -9000,
      payback_time: 120,
    },
  },
  {
    id: 'papa>maiz>frijol',
    metrics: {
      environmental_risk: 0.5,
      soil_degradation: 0.1,
      economic_loss: -8000,
      payback_time: 130,
    },
  },
  {
    id: 'maiz>frijol>papa',
    metrics: {
      environmental_risk: 0.6,
      soil_degradation: 0.4,
      economic_loss: -12000,
      payback_time: 140,
    },
  },
  {
    id: 'frijol>maiz>papa',
    metrics: {
      environmental_risk: 0.7,
      soil_degradation: 0.6,
      economic_loss: -6000,
      payback_time: 90,
    },
  },
  {
    id: 'dominated>route>example',
    metrics: {
      environmental_risk: 0.8,
      soil_degradation: 0.7,
      economic_loss: -4000,
      payback_time: 150,
    },
  },
];

test('rankCandidates changes top rotation when moving each knob (w1..w4)', () => {
  const byRisk = rankCandidates(SAMPLE_CANDIDATES, SAMPLE_BOUNDS, { w1: 100, w2: 0, w3: 0, w4: 0 });
  const bySoil = rankCandidates(SAMPLE_CANDIDATES, SAMPLE_BOUNDS, { w1: 0, w2: 100, w3: 0, w4: 0 });
  const byProfit = rankCandidates(SAMPLE_CANDIDATES, SAMPLE_BOUNDS, { w1: 0, w2: 0, w3: 100, w4: 0 });
  const byPayback = rankCandidates(SAMPLE_CANDIDATES, SAMPLE_BOUNDS, { w1: 0, w2: 0, w3: 0, w4: 100 });

  assert.equal(byRisk[0].id, 'papa>frijol>maiz');
  assert.equal(bySoil[0].id, 'papa>maiz>frijol');
  assert.equal(byProfit[0].id, 'maiz>frijol>papa');
  assert.equal(byPayback[0].id, 'frijol>maiz>papa');

  for (const ranked of [byRisk, bySoil, byProfit, byPayback]) {
    assert.equal(
      ranked.some((item) => item.id === 'dominated>route>example'),
      false,
      'Dominated candidate should be excluded from the Pareto front',
    );
  }
});

test('rankCandidates omits missing economic_loss and returns empty when active weight is zero', () => {
  const noEconCandidates = [
    {
      id: 'b>route',
      metrics: { environmental_risk: 0.3, soil_degradation: 0.2, economic_loss: null, payback_time: 100 },
    },
    {
      id: 'a>route',
      metrics: { environmental_risk: 0.3, soil_degradation: 0.2, economic_loss: null, payback_time: 100 },
    },
  ];
  const bounds = {
    environmental_risk: [0.3, 0.3],
    soil_degradation: [0.2, 0.2],
    payback_time: [100, 100],
  };

  assert.deepEqual(
    rankCandidates(noEconCandidates, bounds, { w1: 0, w2: 0, w3: 100, w4: 0 }),
    [],
  );

  const tied = rankCandidates(noEconCandidates, bounds, { w1: 50, w2: 50, w3: 0, w4: 0 });
  assert.deepEqual(tied.map((r) => r.id), ['a>route', 'b>route']);
});
