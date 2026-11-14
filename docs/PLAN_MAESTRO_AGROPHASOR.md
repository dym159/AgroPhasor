# Plan maestro de AgroPhasor

## Entrega del proyecto

Una web en la que un agricultor pueda dibujar su parcela, armar un calendario con sus cultivos, simular cómo responde el terreno y comparar su plan con rotaciones sugeridas. El usuario objetivo conoce su terreno y usa el celular para trabajar. La pantalla debe poder usarse con instrucciones breves, nombres familiares y controles táctiles.

La primera entrega demuestra una parcela, dos o más periodos y un catálogo pequeño acordado con Física. La ubicación, los cultivos y la fecha de entrega siguen por confirmar. Empezar con un cultivo por lote y habilitar hasta dos zonas si el simulador y la interfaz superan las pruebas de esa modalidad. El calendario y la selección de rotaciones deben funcionar en móvil y escritorio.

## Secuencia de trabajo

| Hito | Qué se puede hacer en paralelo | Evidencia para cerrarlo |
|---|---|---|
| 1. Fijar el contrato | Física fija unidades, parámetros y caso de referencia. Matemática diseña la integración y las métricas. CC prepara mapa, calendario y API con datos de prueba. | Ejemplo de solicitud y respuesta versionado, con una parcela y dos periodos. Cada equipo sabe qué recibe y qué entrega. |
| 2. Resolver el caso mínimo | Física y Matemática verifican una celda y los saltos de cosecha y siembra. CC integra NASA POWER, prueba el flujo visual y prepara despliegue. | Caso base y caso de estrés reproducibles, con resultados de referencia por variable y tolerancias. |
| 3. Integrar la rotación | CC conecta el motor por celda y los resultados por periodo. Matemática verifica el buscador y el frente de Pareto. | El recorrido completo compara el plan manual y las recomendaciones con el motor real. |
| 4. Validar y publicar | El equipo ejecuta pruebas científicas, de API, de interfaz y de rendimiento. Una persona del perfil objetivo prueba la pantalla. | Demo desplegada, fuentes atribuidas, resultados reproducibles y recorrido de respaldo probado. |
| 5. Probar adopción | Tras la demo, preparar un piloto con una cooperativa o un técnico que atienda varias parcelas. | Evidencia de uso para decidir una siembra y de disposición a pagar por repetir el servicio. |

## Física · definir el comportamiento del terreno

1. **Fijar el estado por celda.** Usar temperatura del dosel `T` (°C), humedad radicular `W` (mm), nutrientes `N, P, K` (kg/ha), biomasa aérea `B` (t/ha) y espesor fértil `H` (mm). Son cinco bloques y siete componentes escalares. Documentar condiciones iniciales, unidades, rangos y la hipótesis de columnas 2.5D desacopladas. Identificar datos observados, estimaciones y supuestos.
2. **Cerrar los balances.** Entregar la versión aprobada de las ecuaciones de energía, agua, nutrientes, biomasa y erosión, con las relaciones de cierre del PDF. Para cada término indicar significado, unidad, signo, rango, fuente y parámetro ajustable. Aclarar qué controles corresponden al manejo —riego, fertilización y rastrojo— y qué valores describen terreno o un escenario hipotético.
3. **Resolver las transiciones.** En cosecha, registrar el rendimiento definido por el índice de cosecha, calcular el rastrojo y activar el régimen de transición. En siembra, inicializar la biomasa basal y activar los parámetros del siguiente cultivo. Definir cómo contabilizar la materia orgánica incorporada en la siembra, ya que la especificación también usa materia orgánica como propiedad del terreno. Acordar qué estado sigue entre periodos y qué cambia en cada evento. Distinguir biomasa verde de rastrojo al calcular cobertura y erosión durante la transición.
4. **Entregar el catálogo inicial.** Por cultivo, registrar familia, duración, calendario, coeficientes y umbrales por etapa, biomasa basal y máxima e índice de cosecha. Definir qué restricciones son obligatorias para una recomendación y qué riesgos se informan. Registrar contexto y excepciones para reglas agronómicas como la repetición de familia.
5. **Cerrar las salidas explicables.** Definir escudo/índice ambiental, humedad, estrés por calor, fertilidad, crecimiento, erosión y alerta de riego. Para cada indicador acordar fórmula, unidades, umbral, escala espacial y texto que verá el agricultor. Etiquetar los resultados del modelo como estimaciones.
6. **Entregar casos de referencia.** Una celda en condiciones base y otra bajo estrés, con entradas y salidas esperadas y un evento cosecha–siembra. Incluir un caso de lluvia en pendiente con distinta cobertura. Validar órdenes de magnitud, balances y plausibilidad agronómica antes de usar los resultados en la demo.

## Matemática · convertir el modelo en un cálculo verificable

1. **Especificar el sistema híbrido.** Fijar el modo discreto de cultivo o transición, la semántica de las fechas y el orden de actualización en los eventos. Documentar qué acoplamientos se actualizan por paso y bajo qué hipótesis se aplica el integrador exponencial de NPK. Seleccionar el integrador para el resto, su paso y sus tolerancias. Comparar con un paso más fino y revisar convergencia y no negatividad. Registrar excedentes, agotamiento o inviabilidad según el balance físico.
2. **Verificar los escenarios climáticos.** Preparar un caso histórico y escenarios de estrés con hipótesis explícitas. Si se usa FFT más perturbaciones, documentar el periodo de ajuste, la semilla y la construcción de la precipitación y temperatura. Verificar estacionalidad, magnitud y persistencia de los extremos. Si se muestra un porcentaje, definirlo como una frecuencia dentro de los escenarios probados y explicar qué evento se contó.
3. **Definir el problema de rotación.** Una candidata contiene cultivos, fechas, transición y estado heredado por lote o zona. Incorporar cultivos fijados por el agricultor, duraciones y restricciones. Precisar si una violación de umbral invalida la secuencia o genera una alerta, cómo se evalúa entre celdas y escenarios, y qué devuelve el motor si todas las rotaciones son inviables.
4. **Cerrar las cuatro métricas.** Documentar cómo se minimizan estrés climático e hídrico, degradación del suelo, déficit económico y duración del ciclo. Acordar agregación espacial y temporal, referencias de normalización, tratamiento de métricas constantes, desempates y combinación de escenarios. Calcular margen con ingresos menos costos cuando hay datos locales suficientes. El modo **Mayor Ganancia** depende de esa disponibilidad.
5. **Verificar búsqueda y Pareto.** Enumerar un catálogo pequeño y obtener un frente de referencia. Comparar factibilidad, métricas y candidatas no dominadas con la búsqueda. Antes de atribuir optimalidad a A*, definir el estado, las aristas, el costo y la heurística, y justificar la poda para el resultado buscado. Documentar cuándo la búsqueda entrega un subconjunto aproximado. Usar la enumeración como referencia de la demo si el catálogo sigue siendo pequeño.
6. **Fijar prioridades.** Entregar pesos no negativos que sumen uno para **Máxima Resiliencia**, **Balance Óptimo** y **Mayor Ganancia**. Las perillas reordenan las candidatas ya simuladas. Las combinaciones de pesos solamente seleccionan entre las alternativas evaluadas que minimizan su suma ponderada. Conservar el conjunto de candidatas para que el panel pueda comparar opciones.

## CC · llevarlo a la web

| Frente | Trabajo y resultado | Linear |
|---|---|---|
| Repositorio y entorno | Hooks de Git, gestión de configuración y credenciales, entorno reproducible y CI en pull requests. | [CC-01](https://linear.app/nasa-challengue-tasks/issue/NAS-6), [CC-11](https://linear.app/nasa-challengue-tasks/issue/NAS-16), [CC-13](https://linear.app/nasa-challengue-tasks/issue/NAS-18) |
| Contrato y API | Validar GeoJSON, geometría y fechas, definir lotes, zonas, periodos y cultivos fijados. Vincular resultados, alertas y eventos al periodo. Probar respuestas para datos faltantes, geometría inválida y ausencia de rotaciones viables. | [CC-02](https://linear.app/nasa-challengue-tasks/issue/NAS-7), [CC-05](https://linear.app/nasa-challengue-tasks/issue/NAS-10) |
| Datos | Integrar NASA POWER con datos guardados para reproducibilidad. Evaluar SRTM para elevación y pendiente y el contraste de humedad con SMAP a escala compatible. Para las demás fuentes, registrar cobertura local, resolución, fecha, unidades, atribución y política de huecos. Priorizar las entradas que exige el caso mínimo. | [CC-06](https://linear.app/nasa-challengue-tasks/issue/NAS-11), [CC-14](https://linear.app/nasa-challengue-tasks/issue/NAS-19), [CC-15](https://linear.app/nasa-challengue-tasks/issue/NAS-20) |
| Motor | Implementar la integración por celda, los eventos, los escenarios y la agregación según los casos aprobados por Física y Matemática. Servir los resultados mediante la API y medir duración para tamaños de malla y horizontes documentados. | [CC-07](https://linear.app/nasa-challengue-tasks/issue/NAS-12) |
| Mapa y parcelas | Mapa satelital, ubicación opcional y dibujo, edición y confirmación táctil de lotes. Permitir ubicar la parcela manualmente si se rechaza la geolocalización. | [CC-03](https://linear.app/nasa-challengue-tasks/issue/NAS-8), [CC-04](https://linear.app/nasa-challengue-tasks/issue/NAS-9) |
| Planificación | Implementar asignación de cultivos, calendario, simulación manual, comparación de rotaciones y aplicación explícita de la sugerencia. Mostrar el motivo, las fechas y los cultivos. | [CC-09](https://linear.app/nasa-challengue-tasks/issue/NAS-14) |
| Tablero y visor | Conectar el periodo activo al estado de la parcela, al visor 2.5D/3D y a los indicadores. Seleccionar prioridades sin repetir la simulación. Aplicar cambios de escenario con una nueva simulación. | [CC-08](https://linear.app/nasa-challengue-tasks/issue/NAS-13), [CC-20](https://linear.app/nasa-challengue-tasks/issue/NAS-25), [CC-21](https://linear.app/nasa-challengue-tasks/issue/NAS-26) |
| Pruebas y despliegue | Verificar API, motor, optimizador y recorrido móvil. Desplegar la demo, verificar configuración, medir con caché fría y caliente y probar el respaldo. | [CC-10](https://linear.app/nasa-challengue-tasks/issue/NAS-15), [CC-12](https://linear.app/nasa-challengue-tasks/issue/NAS-17) |

### Recorrido del agricultor

1. **Dibuja tu parcela.** El mapa permite dibujar o editar el lote y confirmar su forma.
2. **Arma tu calendario.** Debajo de la tierra aparecen los periodos. La escala del periodo activo tiene **una marca por cada mes**, con etiquetas como **Ene · Feb · Mar**. Cada periodo tiene sus fechas. **+ Agregar periodo** va al costado, al final de la lista de periodos.
3. **Elige tus cultivos.** Arriba a la derecha están los cultivos disponibles. Al tocar uno se asigna al periodo activo, con zona si corresponde. El usuario puede fijar una decisión de siembra.
4. **Revisa cómo está tu parcela.** El centro muestra el terreno y la izquierda muestra los indicadores del periodo activo con texto y color. Debajo van los tres modos visibles y las perillas de preferencias desplegables. En **Simular otro escenario** se ajustan clima o manejo.
5. **Compara y decide.** Abajo a la derecha se muestra la rotación sugerida. Revisar su secuencia y el motivo, compararla con el plan actual y aplicarla con un botón explícito. En móvil, mantener el mismo recorrido con secciones apiladas y controles táctiles. Ofrecer selección por toque además de cualquier opción de arrastrar.

### Pruebas para cerrar la entrega

- [ ] Física firma las ecuaciones, parámetros y tolerancias del caso base y del caso bajo estrés.
- [ ] Con dos periodos, la prueba del motor registra cosecha, rastrojo y siembra. Confirma que humedad, nutrientes y capa fértil pasan correctamente entre periodos.
- [ ] El catálogo pequeño permite reproducir el frente de Pareto. Se comprueba el descarte de secuencias inviables y el tratamiento de costos faltantes.
- [ ] Cambiar un modo o una prioridad reutiliza la simulación. Aplicar un cambio de escenario actualiza los resultados tras simular de nuevo.
- [ ] Un productor del perfil objetivo puede, desde el celular y sin explicación previa, dibujar un lote, crear dos periodos, identificar sus meses, asignar cultivos e interpretar una sugerencia. Registrar dónde duda o se equivoca.
- [ ] La demo identifica qué datos son observados, estimados o de respaldo. El video o guion de presentación, la documentación técnica y la demo muestran el mismo recorrido. Confirmar con las bases vigentes el formato y los entregables oficiales antes de enviar.

## Ruta crítica y reparto inicial

**Física y Matemática:** cerrar primero la hoja de variables, ecuaciones y eventos y entregar un caso de una celda, dos periodos y datos reproducibles. CC usa ese caso como prueba al sustituir los datos de ejemplo por el motor real.

**Tu frente de producto y CC:** coordinar el contrato de CC-02 con tus compañeros, dejar lista la interfaz con datos de prueba y recorrerla en móvil. En paralelo se pueden construir el mapa, la API, el adaptador de datos y el comparador de rotaciones. Los datos de prueba deben estar identificados durante la demo.

**Integración conjunta:** contrato → motor de una celda y saltos → malla y escenarios → optimización y comparación → prueba con agricultor → despliegue. En cada entrega, el equipo que recibe valida el ejemplo reproducible del equipo que entrega.

**Trabajo posterior al recorrido principal:** capas GIBS, alertas en movimiento, asistente y diagnóstico por WhatsApp quedan en [CC-16](https://linear.app/nasa-challengue-tasks/issue/NAS-21), [CC-17](https://linear.app/nasa-challengue-tasks/issue/NAS-22), [CC-18](https://linear.app/nasa-challengue-tasks/issue/NAS-23) y [CC-19](https://linear.app/nasa-challengue-tasks/issue/NAS-24). Hardware, háptica y escenarios Artemis pueden evaluarse cuando se cierre la demo central.

## Piloto y modelo de negocio

Probar una licencia por campaña con una cooperativa, por tramos de parcelas activas. La cooperativa contrata, un técnico acompaña y el agricultor construye o revisa el calendario. Para un primer piloto, elegir una zona con un socio dispuesto a facilitar casos reales. Entregar por parcela la comparación del plan habitual con las alternativas y un calendario fácil de compartir. Medir cuántos completan el plan, qué decisión de siembra toman con él y si la organización paga por renovar. Definir el precio a partir del piloto.

## Referencias

- [Documento técnico de AgroPhasor](referencias/Agrophasor%20(2).pdf), especialmente §§2.6 y 3–8.
- [Matriz de fuentes para la implementación](referencias/CAMBIOS_APIS_MATRIZ_NASA.md) y [guía de datos agrícolas](referencias/NASA_Field_Shift_Guia_Datos_Agricolas.md).
- [Proyecto AgroPhasor · CC en Linear](https://linear.app/nasa-challengue-tasks/project/agrophasor-cc-bc98b7d10b09).
