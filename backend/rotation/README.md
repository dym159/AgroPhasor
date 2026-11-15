# Rotaciones exactas

`POST /api/v1/parcelas/rotaciones` mantiene intacto `/api/v1/rotaciones`.
El grafo implícito usa DFS exacta, prohíbe familias consecutivas y encadena
duración del catálogo + transición. Los índices de `fixed` empiezan en cero.

Entrada mínima (números ilustrativos de contrato, no mediciones):

```json
{
  "m": 3, "start_date": "2026-11-15", "crop_ids": ["papa", "maiz", "frijol"],
  "latitude": -12.06, "longitude": -75.21,
  "initial_state": {"W": 100, "N": 100, "P": 40, "K": 120,
                    "H": 400, "residue": 0, "OM": 3},
  "transition_days": 14, "residue_fraction": 0.5, "slope_deg": 0,
  "irrigation_mm_day": 0, "irrigation_cost_usd_mm_ha": 0,
  "fixed": {"0": "papa"}, "route": "B_balance"
}
```

W y H en mm; NPK en kg/ha; rastrojo en t/ha; OM en porcentaje.
Precios `prices_usd_t` en USD/t, costos `costs_usd_ha` en USD/ha:
se requieren explícitos para evitar usar valores económicos de respaldo como
datos observados. Si faltan, f3 es None globalmente, C2 se deshabilita y los
pesos activos se renormalizan. Pesos `weights`: cuatro números que suman uno.

Opcionales: `geometry` GeoJSON Polygon/MultiPolygon (se usa su centroide climático),
`windows` por cultivo con meses 1..12, `drought_days` (criterio de inviabilidad),
`survival_threshold` (0,1], `aggregation`: mean/worst.
`periods`: lista de `{ "start": "AAAA-MM-DD" }` de longitud m; si se aporta,
solo se admiten ramas cuyas fechas encadenadas coinciden exactamente. No se
inserta espera silenciosa ni se cambia la duración física del catálogo.
`scenarios`: lista de objetos `{id, daily: {"MM-DD": [lluvia_mm, T_C, HR_pct, radiación_MJ_m2]}}`.
Sin escenarios explícitos se utiliza el cargador NASA existente. No se generan
perturbaciones nuevas ni se llama a red en tests. Los escenarios suministrados
deben cubrir todas las fechas encadenadas; un dato ausente produce error claro.

Conexión real: `PeriodSimulator` llama `advance_day`, `execute_harvest_event`
e `incorporate_residue` existentes. Conserva W/NPK/H, historia térmica, rastrojo
y OM; la siembra incorpora rastrojo y reinicia biomasa con B0 del catálogo.
Las constantes y supuestos internos son los del motor existente.
g1 integra 1-Psi por día incluyendo transición; g3 es costo menos ingreso;
g4 cuenta días. g2 registra el indicador de suelo por periodo para diagnóstico;
**f2 se recalcula desde el estado final** con `compute_soil_pareto_metric_f2`,
no sumando déficits finales repetidos. f1=Σg1/Σg4, f3=365Σg3/Σg4, f4=Σg4/m.
Media/peor caso de objetivos se calcula sobre escenarios supervivientes y se
reporta su frecuencia respecto al total de escenarios probados.

Cambiar ruta/perillas reutiliza la caché física LRU (16 entradas, por proceso).
La selección pura también funciona directamente sobre el frente retornado.
No hay datos sintéticos en producción: solo en tests. El catálogo existente
y NASA no se modifican. No hay modelo espacial nuevo: el endpoint modela una
columna con pendiente suministrada; no agrega una malla heterogénea.

Pruebas: `python -m pytest tests/test_rotation_graph.py` y `bash ./check-ci.sh`.
Pendiente: NAMOA* (`astar` rechaza su ejecución explícitamente). Requiere cotas
inferiores por etapa válidas incluso con ingresos y poda solo para estados
heredados equivalentes; dominancia de costos sola no basta.
Pendientes de integración: escenarios Fourier/Montecarlo como proveedor público,
malla de referencia y presupuesto de rendimiento (no definidos en este contrato).
