const dateFormat = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeZone: 'UTC' });

export function monthStart(year, monthIndex) {
  return `${String(year).padStart(4, '0')}-${String(monthIndex + 1).padStart(2, '0')}-01`;
}

export function addDays(start, days) {
  const date = new Date(start);
  date.setUTCDate(date.getUTCDate() + days);
  return date.getUTCFullYear() <= 9999 ? date.toISOString().slice(0, 10) : null;
}

export function formatPhaseDate(date) {
  return dateFormat.format(new Date(date));
}

export function daysBetween(start, end) {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86400000);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function lerpArray(arrA, arrB, t, decimals = 3) {
  if (!Array.isArray(arrA) || !Array.isArray(arrB) || arrA.length !== arrB.length) {
    return arrA ?? arrB;
  }
  const factor = 10 ** decimals;
  return arrA.map((v, i) => Math.round(lerp(v, arrB[i], t) * factor) / factor);
}

export function applyTimelineSnapshot(baseResult, targetDate) {
  const snapshots = baseResult?.timeline_snapshots;
  if (!Array.isArray(snapshots) || !snapshots.length || !targetDate) {
    return baseResult;
  }
  const firstDate = snapshots[0].date;
  const targetOffset = daysBetween(firstDate, targetDate);

  let snapA = snapshots[0];
  let snapB = snapshots[snapshots.length - 1];
  for (let i = 0; i < snapshots.length; i++) {
    const s = snapshots[i];
    if (s.day_index <= targetOffset) snapA = s;
    if (s.day_index >= targetOffset) {
      snapB = s;
      break;
    }
  }

  const sameRegime = snapA.phase === snapB.phase && snapA.phase_index === snapB.phase_index;
  const span = snapB.day_index - snapA.day_index;
  const t = sameRegime && span > 0 ? Math.max(0, Math.min(1, (targetOffset - snapA.day_index) / span)) : 0;
  const ref = t > 0.5 && !sameRegime ? snapB : snapA;

  const baseCells = baseResult.cells || [];
  const cells = baseCells.map((baseCell, idx) => {
    const cA = snapA.cells?.[idx];
    const cB = snapB.cells?.[idx];
    if (!cA) return baseCell;
    if (!cB || t === 0 || !sameRegime) {
      const chosen = ref.cells?.[idx] ?? cA;
      return { ...baseCell, ...chosen };
    }
    return {
      ...baseCell,
      ...cA,
      soil_water_mm: Number(lerp(cA.soil_water_mm, cB.soil_water_mm, t).toFixed(2)),
      nutrientes_n_kg_ha: Number(lerp(cA.nutrientes_n_kg_ha, cB.nutrientes_n_kg_ha, t).toFixed(2)),
      nutrientes_p_kg_ha: Number(lerp(cA.nutrientes_p_kg_ha, cB.nutrientes_p_kg_ha, t).toFixed(2)),
      nutrientes_k_kg_ha: Number(lerp(cA.nutrientes_k_kg_ha, cB.nutrientes_k_kg_ha, t).toFixed(2)),
      biomass_t_ha: Number(lerp(cA.biomass_t_ha, cB.biomass_t_ha, t).toFixed(3)),
      canopy_cover_pct: Number(lerp(cA.canopy_cover_pct ?? 0, cB.canopy_cover_pct ?? 0, t).toFixed(1)),
      ndvi_satelital: Number(lerp(cA.ndvi_satelital ?? 0.15, cB.ndvi_satelital ?? 0.15, t).toFixed(3)),
      h_current_mm: Number(lerp(cA.h_current_mm, cB.h_current_mm, t).toFixed(4)),
      accumulated_erosion_mm: Number(lerp(cA.accumulated_erosion_mm, cB.accumulated_erosion_mm, t).toFixed(4)),
      rain_height_variation_mm: Number(lerp(cA.rain_height_variation_mm ?? 0, cB.rain_height_variation_mm ?? 0, t).toFixed(4)),
      visual_height_delta_m: Number(lerp(cA.visual_height_delta_m ?? 0, cB.visual_height_delta_m ?? 0, t).toFixed(5)),
      soil_vitality_index: Number(lerp(cA.soil_vitality_index ?? 1, cB.soil_vitality_index ?? 1, t).toFixed(4)),
      soil_color_rgb: cA.soil_color_rgb.map((ch, i) => Math.round(lerp(ch, cB.soil_color_rgb[i], t))),
      base_soil_color_rgb: (cA.base_soil_color_rgb ?? cA.soil_color_rgb).map((ch, i) =>
        Math.round(lerp(ch, (cB.base_soil_color_rgb ?? cB.soil_color_rgb)[i], t))
      ),
      shield_enabled: cA.shield_enabled,
      eta_lissajous: Number(lerp(cA.eta_lissajous ?? 0, cB.eta_lissajous ?? 0, t).toFixed(4)),
      shield_score: Number(lerp(cA.shield_score ?? 0, cB.shield_score ?? 0, t).toFixed(4)),
      hourly_environmental_index: lerpArray(cA.hourly_environmental_index, cB.hourly_environmental_index, t, 4),
      hourly_shield_score: cA.hourly_shield_score && cB.hourly_shield_score
        ? lerpArray(cA.hourly_shield_score, cB.hourly_shield_score, t, 4)
        : (cA.hourly_shield_score ?? cB.hourly_shield_score),
      hourly_air_temps: lerpArray(cA.hourly_air_temps, cB.hourly_air_temps, t, 2),
      hourly_canopy_temps: lerpArray(cA.hourly_canopy_temps, cB.hourly_canopy_temps, t, 2),
      lissajous_area: Number(lerp(cA.lissajous_area, cB.lissajous_area, t).toFixed(3)),
      mean_canopy_temp: Number(lerp(cA.mean_canopy_temp, cB.mean_canopy_temp, t).toFixed(2)),
      eta_nutrientes: Number(lerp(cA.eta_nutrientes, cB.eta_nutrientes, t).toFixed(4)),
      water_condition_index: Number(lerp(cA.water_condition_index ?? 1, cB.water_condition_index ?? 1, t).toFixed(4)),
      is_irrigation_needed: t < 0.5 ? cA.is_irrigation_needed : cB.is_irrigation_needed,
      suggested_irrigation_mm: Number(lerp(cA.suggested_irrigation_mm, cB.suggested_irrigation_mm, t).toFixed(2)),
    };
  });

  return {
    ...baseResult,
    date: targetDate,
    phase_index: ref.phase_index,
    phase: ref.phase,
    crop: ref.crop,
    crop_id: ref.crop_id,
    lot_mean_soil_water_mm: Number(lerp(snapA.lot_mean_soil_water_mm, snapB.lot_mean_soil_water_mm, t).toFixed(2)),
    lot_mean_n_kg_ha: Number(lerp(snapA.lot_mean_n_kg_ha, snapB.lot_mean_n_kg_ha, t).toFixed(2)),
    lot_mean_p_kg_ha: Number(lerp(snapA.lot_mean_p_kg_ha, snapB.lot_mean_p_kg_ha, t).toFixed(2)),
    lot_mean_k_kg_ha: Number(lerp(snapA.lot_mean_k_kg_ha, snapB.lot_mean_k_kg_ha, t).toFixed(2)),
    lot_mean_biomass_t_ha: Number(lerp(snapA.lot_mean_biomass_t_ha, snapB.lot_mean_biomass_t_ha, t).toFixed(2)),
    lot_mean_canopy_cover_pct: Number(lerp(snapA.lot_mean_canopy_cover_pct ?? 0, snapB.lot_mean_canopy_cover_pct ?? 0, t).toFixed(1)),
    lot_mean_h_mm: Number(lerp(snapA.lot_mean_h_mm, snapB.lot_mean_h_mm, t).toFixed(3)),
    lot_mean_accumulated_erosion_mm: Number(
      lerp(snapA.lot_mean_accumulated_erosion_mm ?? 0, snapB.lot_mean_accumulated_erosion_mm ?? 0, t).toFixed(3)
    ),
    lot_mean_temp: Number(lerp(snapA.lot_mean_temp, snapB.lot_mean_temp, t).toFixed(2)),
    lot_mean_eta_nutrientes: Number(lerp(snapA.lot_mean_eta_nutrientes, snapB.lot_mean_eta_nutrientes, t).toFixed(3)),
    irrigation_alert: t < 0.5 ? snapA.irrigation_alert : snapB.irrigation_alert,
    suggested_irrigation_mm: Number(lerp(snapA.suggested_irrigation_mm, snapB.suggested_irrigation_mm, t).toFixed(2)),
    cells,
  };
}

export function assignPhaseCrop(phases, index, cropId, cycles) {
  const updated = phases.slice(0, index);
  for (const [offset, phase] of phases.slice(index).entries()) {
    const id = offset === 0 ? cropId : phase.cropId;
    const previous = updated.at(-1);
    const oldEnd = phases[index + offset - 1]?.harvest;
    const gap = oldEnd ? Math.round((Date.parse(phase.start) - Date.parse(oldEnd)) / 86400000) : 0;
    const start = offset === 0 ? phase.start
      : previous.harvest ? addDays(previous.harvest, Math.max(gap, 0))
      : phase.start > previous.start ? phase.start : addDays(previous.start, 1);
    if (!start) return phases;
    const manualEnd = offset > 0 && Boolean(phase.manualEnd);
    const days = manualEnd
      ? Math.round((Date.parse(phase.harvest) - Date.parse(phase.start)) / 86400000)
      : cycles[id];
    const harvest = days ? addDays(start, days) : null;
    updated.push({ ...phase, cropId: id, start, harvest, manualEnd: manualEnd && Boolean(harvest) });
  }
  return updated;
}
