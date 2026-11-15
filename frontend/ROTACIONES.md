# Rotaciones en la interfaz

El panel consume `POST /api/v1/parcelas/rotaciones`. El botón solicita el frente
una vez; se conserva completo en `rotationState`. Los presets usan los pesos
publicados en `recomendada_por_ruta`; no hay copia de los presets en producción.
Cambiar modo o perilla selecciona localmente con la suma ponderada sobre f_hat.
Cambiar clima/manejo vuelve a consultar; respuestas atrasadas se descartan.
Solicitudes idénticas consecutivas en carga o completadas se deduplican.

El panel permite elegir de dos a seis periodos y una fecha inicial, incluso sin
completar el calendario. Las casillas permiten fijar cultivos existentes. Por
defecto el motor calcula fechas encadenadas; solo se envían todos los inicios del
calendario si se marca «Respetar exactamente los inicios del calendario».
Si ninguna secuencia respeta esas fechas y las duraciones del catálogo, se
muestra sin viables con sus motivos.
Aplicar requiere pulsar el botón y conserva una copia del plan para Deshacer.

Los datos iniciales de suelo y manejo se introducen explícitamente, sin valores
físicos inventados. Precios USD/t y costos USD/ha son opcionales; sin economía
se deshabilitan C2, C3 y ganancia. El escenario por defecto es NASA POWER del
servicio; escenarios propios se aportan con el JSON que admite el contrato.
La edición JSON es una limitación de usabilidad del proveedor de escenarios actual.

Limitaciones del contrato que la interfaz muestra expresamente:

- No devuelve la simulación del plan actual. Se compara su secuencia con la
  sugerencia; no se inventan barras ni métricas para el plan actual.
- No devuelve el denominador de escenarios NASA. Se presenta la frecuencia
  retornada; X de N solo aparece con N conocido de escenarios enviados.
- El cálculo representa una columna de suelo y no una malla heterogénea.

Pruebas: `node --test tests/*.mjs` desde la raíz (también `npm test`).
Incluyen vectores sintéticos, rendimiento de selección, estados, peticiones,
respuestas atrasadas, aplicación/restauración y renderizado con un doble DOM.
No requieren dependencias nuevas, navegador ni red.

Pendiente de validación manual: recorrido a 390 px desde dibujo de parcela hasta
aplicar/deshacer. El navegador local no pudo abrirse por permiso rechazado durante
esta sesión. Los estilos apilan el panel y reservan controles de al menos 44 px.
Backend, mapa y visor 3D se mantienen sin cambios.
