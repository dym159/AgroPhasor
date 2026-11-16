export const ROTATION_METRICS = [
  'environmental_risk',
  'soil_degradation',
  'economic_loss',
  'payback_time',
];

const KNOB_KEYS = ['w1', 'w2', 'w3', 'w4'];

function dominates(left, right, metrics) {
  return (
    metrics.every((key) => left.metrics[key] <= right.metrics[key]) &&
    metrics.some((key) => left.metrics[key] < right.metrics[key])
  );
}

function normalizeMetric(value, [low, high]) {
  if (low === high) return 0;
  return Math.max(0, Math.min(1, (value - low) / (high - low)));
}

/**
 * Re-rank already-evaluated rotation candidates using the current knob weights,
 * mirroring backend/rotation_ranking.py so slider updates are instant.
 */
export function rankCandidates(candidates, bounds, knobs) {
  if (!Array.isArray(candidates) || !candidates.length || !bounds) return [];

  const rawValues = KNOB_KEYS.map((key) => Number(knobs?.[key] ?? 0));
  const total = rawValues.reduce((sum, val) => sum + (Number.isFinite(val) && val >= 0 ? val : 0), 0);
  if (total <= 0) return [];

  const weights = Object.fromEntries(
    ROTATION_METRICS.map((metric, idx) => [metric, rawValues[idx] / total])
  );
  const hasEconomics = candidates.every((candidate) => candidate.metrics?.economic_loss != null);
  const comparedMetrics = ROTATION_METRICS.filter((metric) => hasEconomics || metric !== 'economic_loss');
  const activeWeight = comparedMetrics.reduce((sum, metric) => sum + weights[metric], 0);
  if (activeWeight <= 0) return [];

  const front = candidates.filter(
    (candidate) => !candidates.some((other) => dominates(other, candidate, comparedMetrics))
  );

  const scored = front.map((candidate) => {
    const score =
      comparedMetrics.reduce((sum, metric) => {
        const normalized = normalizeMetric(candidate.metrics[metric], bounds[metric] ?? [0, 0]);
        return sum + weights[metric] * normalized;
      }, 0) / activeWeight;
    return { candidate, score };
  });

  scored.sort((a, b) => {
    if (a.score !== b.score) return a.score - b.score;
    return a.candidate.id < b.candidate.id ? -1 : a.candidate.id > b.candidate.id ? 1 : 0;
  });

  return scored.map(({ candidate }) => candidate);
}
