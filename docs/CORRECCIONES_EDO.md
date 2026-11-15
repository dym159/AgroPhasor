# Correcciones de las EDO según la auditoría del 15-11-2026

La referencia matemática es el PDF de 53 páginas aportado por el usuario.
Estos cambios corrigen los hallazgos reproducidos; no constituyen calibración
con mediciones de campo ni certificación general de exactitud agronómica.

## Ecuaciones y diagnósticos

- EDO1 aplica la solución con Qlat congelado al inicio (sección 4.2). Se retiró
  la sustitución por Penman. La conductancia es cero bajo marchitez y de noche;
  la rampa diurna coincide con la usada en el balance hídrico.
- EDO2 conserva la integral exponencial y el límite lineal cuando lambda=0.
  Si W se agota en ese caso, se limita el tiempo de transpiración al tiempo
  real de agotamiento. Los flujos y W mantienen precisión de coma flotante.
- EDO3 usa expm1 para phi1 y calcula los diagnósticos con la integral exacta del
  estado X'=S-lambda*X. Se eliminó el factor 0,10 que afectaba la lixiviación
  reportada. Las salidas sources_npk_kg_ha, uptake_npk_kg_ha y erosion_npk_kg_ha
  permiten comprobar el balance de cada nutriente, junto con la lixiviación.
- EDO4 usa kdec recibido sin multiplicarlo por Q10 en transición, permite km=0
  y conserva el rastrojo heredado aunque supere Bmax del siguiente cultivo.
  Crecimiento y mantenimiento se integran sobre B(t); no son flujos Euler.
- EDO5 informa dh_dt_mm_day como tasa media efectiva (H1-H0)/dt, incluso cuando
  se alcanza H=0. El diagnóstico aislado de arrastre integra X'=-xi*Hloss*X;
  cuando existen otras fuentes y pérdidas, el balance completo pertenece a EDO3.
- Los estados W, NPK, B y H, cosecha y rastrojo no se redondean durante su
  propagación. Los formatos visuales pueden seguir redondeando para mostrar.

## Acoplamiento

advance_day acepta dt_days, por defecto un día. El esquema es multiescala:

1. Hidrología, erosión, química y biomasa usan los estados lentos del inicio.
2. La temperatura conserva memoria y se subintegra con estados lentos y
   forzantes congelados. Cada subpaso usa la expresión térmica del PDF.
3. El tamaño térmico es como máximo 0,5 Cp/(h+lambda_gamma*Delta), una selección
   numérica basada en la rigidez local; Penman solo estima el paso. Se detiene
   la relajación cuando el cambio es <=1e-10 °C bajo forzantes constantes.
4. La erosión enviada a química se divide por dt_days, pasando mm/día y no mm.
5. La salida de agua por reducción de capacidad se suma a water_runoff_mm y se
   identifica también como capacity_runoff_mm. Los restantes flujos están en
   water_infiltration_mm, water_etc_mm y water_drainage_mm.
6. El reciclaje de K del rastrojo utiliza la biomasa media exacta de transición,
   correspondiente al rastrojo realmente descompuesto durante el intervalo.
7. Psi al final usa los límites hídricos del espesor actualizado.

El contrato de cinco componentes de estado se conserva. Su último componente
history admite temperaturas históricas antiguas como números y nuevas entradas
(temperatura_aire, temperatura_dosel). Esta pareja conserva T entre pasos sin
añadir un sexto componente que rompa los adaptadores. La API de rotación acepta
ambas representaciones. La temperatura del suelo continúa siendo un proxy de
promedio del historial de aire; no es una medición ni una EDO térmica del suelo.

Las forzantes diarias no contienen extremos horarios. El subpaso térmico mejora
la integración de esas forzantes constantes y no inventa variación intradiaria.
El paso diario de estados lentos sigue siendo una aproximación de primer orden;
dt_days permite refinarlo. La prueba de convergencia usa condiciones controladas,
no garantiza precisión universal para cualquier forzante o tamaño de paso.

## Validación reproducible

Ejecutar `.venv/Scripts/python.exe -m pytest tests` en Windows. La suite
test_edo_pdf_regressions.py comprueba solución térmica, balances de agua y NPK,
descomposición, mantenimiento nulo, flujos de biomasa, frontera de erosión,
memoria térmica y disminución del error para pasos 1, 1/2 y 1/4 de día frente
a una referencia de 1/128 de día.

No se modificaron precios, familias, ciclos ni constantes del catálogo.
La importación del nuevo gemini-code.json y cosecha múltiple de fresa son tareas
separadas. Permanecen necesarias trazabilidad de parámetros (incluidas absorción
radicular y unidades de mineralización), validación de campo y análisis para
escenarios climáticos reales antes de usar estas estimaciones operativamente.
