// Cliente HTTP de la simulación de parcela, recomendaciones y búsqueda de localidades.

import { STRATEGY_MODES } from '../data/mockVisualData.js';

export async function fetchCropCycles() {
  const response = await fetch('/api/v1/crop-cycles');
  if (!response.ok) throw new Error('No se pudo cargar la duración de los cultivos.');
  return response.json();
}

export function parcelToGeoJsonGeometry(parcel) {
  if (!parcel?.polygon || parcel.polygon.length < 3) return null;

  const ring = parcel.polygon.map(([lat, lng]) => [Number(lng), Number(lat)]);
  const [firstLng, firstLat] = ring[0];
  const [lastLng, lastLat] = ring[ring.length - 1];
  if (firstLng !== lastLng || firstLat !== lastLat) {
    ring.push([firstLng, firstLat]);
  }

  return {
    type: 'Polygon',
    coordinates: [ring],
  };
}

export async function fetchParcelSimulation(parcel, cropId = 'papa', signal, plan = {}) {
  const geometry = parcelToGeoJsonGeometry(parcel);
  if (!geometry) {
    throw new Error('Selecciona o dibuja un polígono válido en el mapa.');
  }

  const response = await fetch('/api/v1/parcelas/simulacion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ geometry, crop_id: cropId, ...plan }),
    signal,
  });

  const data = await response.json().catch(() => null);
  if (!response.ok || !data?.cells?.length) {
    throw new Error(data?.error || data?.detail || 'La simulación de la parcela no está disponible.');
  }
  return data;
}

export async function fetchSimulation(parcel, strategyId, weights, signal) {
  const geometry = parcelToGeoJsonGeometry(parcel);
  const modeSpec = STRATEGY_MODES.find((m) => m.id === strategyId) ?? STRATEGY_MODES[1];

  const payload = {
    lote_seleccionado_id: parcel?.id ?? 'lote-1',
    modo_prioridad: modeSpec.backendMode,
    perillas: weights,
    geo_features: geometry
      ? {
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: { id: parcel.id, name: parcel.name, area_ha: 2.45 },
              geometry,
            },
          ],
        }
      : { type: 'FeatureCollection', features: [] },
  };

  const response = await fetch('/api/v1/simular', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) throw new Error('No se pudo calcular la rotación recomendada.');
  return response.json();
}

export async function searchPlaces(query) {
  const cleanQuery = query.trim();
  if (cleanQuery.length < 2) return [];

  const params = new URLSearchParams({ q: cleanQuery });
  const response = await fetch(`/api/places?${params}`);
  if (!response.ok) {
    throw new Error('Buscador no disponible.');
  }
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

export async function fetchRotation(payload, signal) {
  const response = await fetch('/api/v1/rotaciones', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !Array.isArray(data?.routes)) {
    throw new Error(data?.error || 'No se pudo calcular la rotación.');
  }
  return data;
}
