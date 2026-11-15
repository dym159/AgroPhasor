const dateFormat = new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium', timeZone: 'UTC' });

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
