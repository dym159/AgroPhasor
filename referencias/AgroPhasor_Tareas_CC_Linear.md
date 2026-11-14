# AgroPhasor · Tareas de CC para Linear

Cada encabezado numerado es el título de una tarea. Copia su descripción, prioridad, rol y dependencias al crearla en Linear. Los roles indican quién debería tomar cada tarea. El equipo asigna a las personas.

**Prioridades.** Alta para el alcance de la demo, sus pruebas y el despliegue. Media para validaciones adicionales y automatización. Baja para mejoras que se toman si queda tiempo.

## Secuencia de trabajo

1. Configurar los hooks y cerrar el contrato del simulador. Confirmar la parcela de referencia y los casos base y de estrés.
2. Trabajar en paralelo en mapa y dibujo, API y NASA POWER, tablero con datos de ejemplo, y configuración del entorno de servidor.
3. Implementar y verificar el simulador. Conectar una parcela desde el mapa hasta el resultado mensual y probar una nueva simulación.
4. Incorporar la comparación de rotaciones y cerrar las pruebas locales. El primer despliegue de prueba puede hacerse antes con la ruta de estado.
5. Verificar la demo en la URL publicada. Tomar las mejoras de prioridad media y baja según el tiempo y los resultados.

## CC-01 · Configurar hooks de Git para evitar filtraciones

**Prioridad alta · Infraestructura · Sin dependencias**

**Descripción.** Configurar `pre-commit` con Gitleaks y la revisión de archivos preparados para el commit. Excluir `.env` locales, `.netrc`, archivos de credenciales de Google Cloud y otros archivos privados. Versionar un `.env.example` con valores de ejemplo y documentar cómo activar el hook en cada equipo. Usar salida redactada en el escaneo. Guardar las claves privadas en la configuración del entorno de ejecución.

**Criterios de aceptación**

- [ ] Un secreto de prueba reconocido por el detector bloquea un commit local de prueba y el mensaje explica qué corregir.
- [ ] Un cambio limpio y el archivo de configuración de ejemplo pasan la revisión.
- [ ] El README indica cómo instalar el hook y cómo ejecutar el escaneo manual antes del primer push. El equipo comprueba que cada integrante lo activó.

Referencia de implementación. [Gitleaks](https://github.com/gitleaks/gitleaks)

## CC-02 · Acordar las entradas y salidas del simulador

**Prioridad alta · Backend y simulador · Sin dependencias**

**Descripción.** Coordinar con Física la especificación que CC implementará. Documentar componentes del estado, unidades, fuentes, valores iniciales, paso de tiempo, agregación mensual, horizonte de uno a tres años, parámetros editables, cálculo del riesgo y criterios de rotación. La guía nueva identifica temperatura, humedad del suelo y nutrientes como las tres variables mostradas. Confirmar el estado interno y el método de resolución con Física. Mantener diferenciadas temperatura del aire y temperatura de la planta, así como humedad relativa y humedad del suelo.

**Criterios de aceptación**

- [ ] Hay ejemplos compartidos de solicitud y respuesta JSON y un contrato de lotes GeoJSON.
- [ ] La respuesta identifica lote, escenario, mes y año, tres variables con unidades, riesgo, motivos, fuente y avisos de datos o incertidumbre.
- [ ] CC tiene acceso a los dos casos de referencia, sus resultados y tolerancias antes de cerrar la implementación del cálculo.

## CC-03 · Mostrar el mapa satelital y ofrecer ubicación opcional

**Prioridad alta · Frontend y mapas · Sin dependencias**

**Descripción.** Implementar el mapa con Leaflet y la capa Esri World Imagery indicada en la guía. Comprobar disponibilidad, condiciones de uso y atribución del servicio elegido. Permitir zoom y navegación libre. Añadir «Usar mi ubicación» para centrar el mapa con permiso del navegador. Mantener el dibujo manual disponible si el usuario rechaza la ubicación, falla o tarda demasiado.

**Cómo obtener el fondo satelital.** Abre [una tesela de ejemplo de Esri World Imagery](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/0/0/0) para comprobar el servicio indicado en la guía. En Leaflet, configura `L.tileLayer` con `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` y conserva la atribución del proveedor. Verifica el servicio y sus condiciones para el despliegue. Para centrar el mapa, llama a `navigator.geolocation.getCurrentPosition` desde el botón en una página HTTPS y maneja tanto el éxito como el rechazo. [Leaflet](https://leafletjs.com/reference) · [Geolocalización](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition)

**Criterios de aceptación**

- [ ] El mapa carga con atribución visible y permite desplazarse a una zona lejana.
- [ ] Se puede comenzar desde la ubicación del dispositivo o navegando manualmente.
- [ ] Se verifica el permiso concedido y rechazado en la URL HTTPS del despliegue.

## CC-04 · Dibujar, editar y confirmar uno o varios lotes

**Prioridad alta · Frontend y mapas · Depende de CC-02 y CC-03**

**Descripción.** Usar Leaflet-Geoman para dibujar, editar y eliminar contornos. Mantener un polígono y un ID por lote separado. Enviar las coordenadas del contorno confirmado en GeoJSON al servidor y conservar la selección si falla la simulación.

**Criterios de aceptación**

- [ ] El servidor recibe dos lotes separados con sus IDs y los contornos que confirmó el usuario.
- [ ] Una edición aparece en la siguiente confirmación. El usuario puede corregir un contorno inválido.

## CC-05 · Implementar la API y validar las parcelas

**Prioridad alta · Backend · Depende de CC-02**

**Descripción.** Construir la API en Python con FastAPI y Pydantic. Implementar `POST /api/simular` y `GET /api/health`. Validar rangos, orden longitud/latitud de GeoJSON y polígonos. Usar Shapely para seleccionar un punto interior por lote para la consulta inicial. Conservar la geometría confirmada y devolver estado por lote.

**Criterios de aceptación**

- [ ] Una solicitud válida conserva IDs y contornos. Un polígono cruzado o inválido devuelve un error usable por el frontend.
- [ ] Una falla en un lote identifica el lote afectado. La ruta de estado permite comprobar que la aplicación esté disponible sin consultar NASA.

## CC-06 · Integrar NASA POWER y preparar el respaldo de la demo

**Prioridad alta · Backend y datos · Depende de CC-02**

**Descripción.** Consultar la API diaria por punto de NASA POWER con `community=AG`, JSON y HTTPX. Preparar 20 a 30 años de histórico según el período acordado y disponible. Integrar `T2M`, `T2M_MIN`, `T2M_MAX`, `PRECTOTCORR`, `ALLSKY_SFC_SW_DWN`, `RH2M`, `GWETTOP` y `GWETROOT`. Priorizar temperatura, radiación, lluvia y humedad radicular para la primera integración. Leer unidades y valores de relleno desde los metadatos. Registrar coordenadas, período, resolución y origen de cada serie. Ordenar fechas, recortar huecos al final y aplicar la política de imputación acordada antes de Fourier. Preparar un JSON de respaldo con datos reales de la zona de demo, Mantaro o Ica según lo que se elija, además de las respuestas simuladas de prueba.

**Cómo obtener los datos de NASA POWER.**

1. Abre [la consulta de ejemplo para el Valle del Mantaro](https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M,T2M_MIN,T2M_MAX,PRECTOTCORR,ALLSKY_SFC_SW_DWN,RH2M,GWETTOP,GWETROOT&community=AG&longitude=-75.21&latitude=-12.06&start=20200101&end=20200107&format=JSON). La consulta es pública y se puede probar sin clave.
2. En el servidor, usa HTTPX para enviar los mismos parámetros a `/api/temporal/daily/point`. Reemplaza `latitude` y `longitude` por el punto interior del lote y `start` y `end` por el período de fechas acordado en formato `AAAAMMDD`. Valida primero una semana y después descarga el histórico de 20 a 30 años según disponibilidad.
3. Lee las series en `properties.parameter`, donde cada variable contiene valores por fecha. Conserva el período, el estándar temporal, las unidades y el valor de relleno que declara la respuesta. Aplica las conversiones y la limpieza acordadas antes de la FFT.
4. Guarda una respuesta JSON de NASA de la parcela de demo con sus metadatos. Usa los casos guardados para probar varios escenarios y haz una consulta real en la verificación del despliegue. [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)

**Criterios de aceptación**

- [ ] El motor recibe fechas alineadas y unidades verificadas. Un valor de relleno como `-999` queda fuera de la FFT.
- [ ] Una serie insuficiente produce un resultado explícito. El respaldo se identifica como dato histórico guardado y corresponde al punto y período consultados de la demo.
- [ ] Cambiar una condición de la simulación reutiliza la serie disponible para ese lote y período.

Referencia de integración. [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)

## CC-07 · Implementar los escenarios climáticos y el simulador

**Prioridad alta · Programador del simulador · Depende de CC-02 y CC-06 para la integración, puede empezar con datos de prueba**

**Descripción.** Implementar en Python el modelo validado por Física. Usar NumPy para estacionalidad por FFT, tendencia y variación estocástica con semilla reproducible. Incorporar SciPy si el método de resolución acordado lo requiere. Convertir los resultados al nivel mensual y devolver temperatura, humedad del suelo, nutrientes y el riesgo calculado. Validar los resultados antes de serializarlos. Acotar únicamente el indicador que tenga una escala definida y devolver un estado de cálculo inválido ante `NaN` o infinito.

**Criterios de aceptación**

- [ ] El motor reproduce los casos base y de estrés dentro del margen acordado y da el mismo resultado con las mismas entradas y semilla.
- [ ] Una salida no finita se identifica como error de cálculo. Cada variable conserva su unidad y el escenario se identifica como simulación.

## CC-08 · Construir el tablero de riesgo y conectar la resimulación

**Prioridad alta · Frontend y mapas · Depende de CC-02 y CC-03 para la maqueta, de CC-04, CC-05 y CC-07 para la integración**

**Descripción.** Construir el tablero con HTML, CSS y JavaScript. Mostrar un escudo por lote en la demo, una leyenda con texto y color, la línea de tiempo por mes y año y las tres curvas de evolución. Usar una biblioteca ligera como Chart.js si facilita los gráficos. Habilitar los controles de suelo y escenario acordados. Mostrar el estado de carga, el origen de los datos y los avisos del modelo.

**Criterios de aceptación**

- [ ] Se confirma una parcela de punta a punta y el usuario puede cambiar de mes o año.
- [ ] Al ajustar una condición, «Volver a simular» actualiza los resultados asociados al lote y al escenario.
- [ ] Carga, datos insuficientes y error de cálculo se distinguen de los colores del escudo.

## CC-09 · Implementar y explicar las rotaciones recomendadas

**Prioridad alta · Algoritmos y frontend · Depende de CC-02, CC-07 y CC-08**

**Descripción.** Pasar al código los parámetros de cultivo y las restricciones acordadas con Física, con referencias a FAO-56 o FAO GAEZ donde correspondan. Modelar secuencias, calendario, duración, transición y costo. Verificar el orden con un catálogo pequeño antes de ampliar la búsqueda con grafos y A* según la estrategia acordada. Mostrar tarjetas comparables con el motivo de cada recomendación y su evolución mensual.

**Cómo obtener los parámetros de cultivo.** Abre [FAO-56](https://www.fao.org/4/x0490e/x0490e00.htm) y consulta el capítulo 6 y su tabla de coeficientes `Kc` por etapa. Si Física indica usar aptitud agroecológica, busca el cultivo y la zona en [FAO GAEZ](https://gaez.fao.org/). Lleva al catálogo CSV o JSON solo los valores aprobados, con cultivo, etapa, unidad, región y referencia. FAO-56 aporta tablas de referencia para el catálogo.

**Criterios de aceptación**

- [ ] El orden coincide con un ejemplo verificable y se explican las condiciones que favorecen o penalizan cada opción.
- [ ] Se identifica cuándo ninguna secuencia es viable.
- [ ] Elegir otra rotación actualiza la evolución de la opción seleccionada.

## CC-10 · Ejecutar pruebas locales antes de subir cambios

**Prioridad alta · Todo CC · Empieza con CC-02 y se amplía con cada módulo**

**Descripción.** Adaptar de Quippu el patrón de pruebas de contrato, rutas y fallos de dependencias. Usar pytest, FastAPI TestClient y respuestas guardadas de NASA. Ejecutar `python -m pytest -q` y el escaneo de secretos antes del push. Documentar una comprobación manual corta del mapa y el tablero. Automatizar el recorrido de navegador solo si queda tiempo.

**Criterios de aceptación**

- [ ] Geometría y API cubren un lote válido, uno inválido y dos lotes separados.
- [ ] El adaptador de NASA cubre unidades, días faltantes, valores de relleno y tiempo de espera agotado.
- [ ] Se verifican ambos casos de Física, una salida no finita y el orden y descarte de rotaciones.
- [ ] Una prueba llama a `/api/simular` con el motor real y una respuesta guardada de NASA. La suite local puede correr sin claves ni conexión a NASA.
- [ ] El recorrido manual comprueba ubicación rechazada, edición y confirmación, cambio de mes y nueva simulación.

## CC-11 · Configurar el entorno del servidor

**Prioridad alta · Infraestructura y backend · Coordinar con CC-05**

**Descripción.** Preparar un arranque local reproducible con FastAPI y Uvicorn, dependencias fijadas, variables de entorno documentadas y ruta de estado. Evaluar dentro de esta tarea las dos opciones pendientes, frontend y FastAPI en Vercel, o frontend en Vercel y FastAPI en Google Cloud Run. Elegir con una prueba de arranque, disponibilidad de configuración y tiempos del caso de demo. Registrar la opción elegida y el comando o configuración de arranque.

**Criterios de aceptación**

- [ ] Otra persona de CC puede levantar el servicio siguiendo el README.
- [ ] La plataforma elegida admite las dependencias del motor y el caso de demo entra en sus límites de ejecución.
- [ ] El equipo tiene una decisión registrada sobre dónde corre la API y cómo se configura el entorno.

Referencias de plataforma. [FastAPI en Vercel](https://vercel.com/docs/frameworks/backend/fastapi) · [FastAPI en Cloud Run](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-fastapi-service)

## CC-12 · Desplegar y verificar la demo pública

**Prioridad alta · Infraestructura con apoyo de todo CC · Depende de CC-11 para publicar y de CC-08, CC-09 y CC-10 para cerrar la entrega**

**Descripción.** Publicar la arquitectura elegida en CC-11. Si hay servidor separado, conectar las rutas `/api/*` de la web al servicio HTTPS. Configurar las variables del entorno publicado y registrar la revisión desplegada. Medir una primera simulación con la caché vacía y una repetición. Revisar las atribuciones de mapa y datos y preparar un respaldo identificado para la demo.

**Criterios de aceptación**

- [ ] Desde otro dispositivo se puede abrir la web, comprobar `/api/health`, confirmar un lote, simular con NASA y comparar rotaciones.
- [ ] Se prueba el permiso de ubicación y se valida cómo se muestra una consulta fallida o un respaldo.
- [ ] El README registra la URL, la revisión estable y cómo volver a publicarla.

## CC-13 · Repetir las pruebas en pull requests con GitHub Actions

**Prioridad media · Infraestructura · Depende de CC-01 y CC-10**

**Descripción.** Configurar un flujo pequeño que instale las dependencias fijadas y ejecute pytest y el escaneo de secretos en cada pull request. Mantener separados el resultado de pruebas y el paso de publicar. Hacer el chequeo requerido para integrar a `main` si el repositorio permite esa configuración.

**Criterios de aceptación**

- [ ] Un pull request de prueba muestra los resultados y falla cuando se altera un valor esperado.
- [ ] La ejecución usa datos de prueba y valores de ejemplo. El despliegue puede ejecutarse desde el proveedor elegido.

## CC-14 · Contrastar humedad con una muestra de SMAP

**Prioridad media · Backend y datos · Depende de CC-06**

**Descripción.** Evaluar una muestra de humedad superficial o radicular de la zona de estudio con NASA Earthdata Login y `earthaccess`. Compararla con `GWETTOP` o `GWETROOT`, según corresponda, dejando registradas sus diferencias de escala, profundidad, unidades y fechas.

**Cómo descargar una muestra de SMAP.**

1. Crea o usa una cuenta de [NASA Earthdata Login](https://urs.earthdata.nasa.gov/), instala `earthaccess` y autentícate con `earthaccess.login(strategy="interactive")`. Para automatizar, usa las variables de entorno del servicio. Mantén credenciales y archivos de autenticación fuera del repositorio.
2. Busca un producto superficial como `SPL3SMP_E` para Mantaro mediante `earthaccess.search_data(short_name="SPL3SMP_E", bounding_box=(-75.5, -12.3, -74.9, -11.8), temporal=("2020-01-01", "2020-01-07"), count=5)`. Para humedad radicular, busca la colección `SPL4SMGP` y confirma la variable y profundidad en sus metadatos.
3. Selecciona los archivos que cubran fecha y ubicación, y descárgalos con `earthaccess.download(seleccion, local_path="data/smap")`. Revisa unidades, profundidad y marcas de calidad antes de contrastar la muestra con POWER. [Descarga con earthaccess](https://earthaccess.readthedocs.io/en/latest/user/howto/download-to-local-machine/)

**Criterios de aceptación**

- [ ] Queda una comparación reproducible y atribuida. La muestra funciona como validación adicional del caso elegido.

## CC-15 · Evaluar elevación y pendiente con SRTM

**Prioridad media · Backend y datos · Depende de CC-02 y CC-05**

**Descripción.** Obtener la elevación de referencia del lote y evaluar la pendiente si aporta al caso. Pasar estos parámetros al simulador únicamente si están definidos en el contrato. Para la demo, puede bastar una elevación documentada de la parcela de referencia.

**Cómo obtener la elevación de SRTM.** Busca la colección de elevación **SRTMGL1 v003** con `earthaccess.search_data(short_name="SRTMGL1", version="003", bounding_box=(oeste, sur, este, norte))`. Usa el rectángulo del lote en longitud y latitud. Tras autenticarte en Earthdata, descarga la tesela que lo cubre con `earthaccess.download`. Lee el GeoTIFF con Rasterio y muestrea el punto representativo en el sistema de coordenadas del ráster. Verifica que el píxel sea válido y guarda la elevación en metros con su referencia. Si necesitan pendiente, calcúlala con distancias horizontales en metros y documenta cómo se resume dentro del lote. [Producto SRTM de NASA](https://data.nasa.gov/dataset/nasa-shuttle-radar-topography-mission-global-1-arc-second-v003-e47e1)

**Criterios de aceptación**

- [ ] Está documentado el origen del dato y si se usa como contexto o como entrada para heladas o escorrentía.

## CC-16 · Añadir capas visuales de NASA GIBS si sobra tiempo

**Prioridad baja · Frontend y mapas · Depende de CC-08 y CC-12 para priorizar la demo**

**Descripción.** Agregar un selector en Leaflet con teselas WMTS de **MODIS NDVI** para vegetación o **GPM IMERG** para precipitación. Empezar con una capa disponible para la fecha y zona de estudio. Mostrar nombre, fecha, atribución y contexto regional. Usar las teselas para visualización. El cálculo sigue alimentado por las series acordadas.

**Cómo obtener las teselas de NASA GIBS.**

1. Abre el [catálogo WMTS de GIBS para EPSG:3857](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi?SERVICE=WMTS&REQUEST=GetCapabilities). Busca MODIS NDVI o GPM IMERG. Copia el identificador, una fecha disponible, el formato y el conjunto de matrices que declara la capa.
2. Toma la plantilla `ResourceURL` del catálogo. Sustituye `{TileMatrix}`, `{TileRow}` y `{TileCol}` por `{z}`, `{y}` y `{x}` respectivamente si el conjunto es compatible con Leaflet. Prueba una tesela para la zona de estudio y respeta el zoom nativo de la capa.
3. Añade la URL a `L.tileLayer` y registra la capa en `L.control.layers` con fecha y atribución. Usa las teselas desde el frontend. [Acceso a NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/access-basics/)

**Criterios de aceptación**

- [ ] La capa se puede encender y apagar, se distingue del escudo y la selección de lotes funciona en ambos estados.
- [ ] Si la capa falla, puede seguir usándose el mapa base.

Referencia de capas. [NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/)

## CC-17 · Probar alertas en movimiento si sobra tiempo

**Prioridad baja · Frontend y mapas · Depende de CC-08 y CC-12**

**Descripción.** Probar un modo de campo que use la ubicación con permiso y avise al entrar en un lote simulado en riesgo. Añadir vibración en navegadores compatibles y un aviso visible.

**Criterios de aceptación**

- [ ] El modo se puede activar y detener. El aviso visible funciona en un equipo sin vibración.

## CC-18 · Evaluar un asistente de consultas si sobra tiempo

**Prioridad baja · Frontend y backend · Depende de CC-08 y CC-12**

**Descripción.** Probar un asistente para explicar los controles del tablero y el significado del escudo con información del proyecto. Mantener la recomendación de rotación vinculada al resultado del motor.

**Criterios de aceptación**

- [ ] Responde preguntas básicas sobre el tablero y distingue cuándo faltan datos para explicar un resultado.

## Decisiones pendientes que afectan las tareas

- **Resolución visual.** La guía nueva propone escudos por subparcela. El alcance de la demo acordado en el chat lateral usa un punto representativo y un escudo por lote confirmado. Ampliar a sectores cuando los datos o parámetros permitan justificar diferencias entre ellos.
- **Tratamiento de datos.** La guía muestra dos métodos para rellenar huecos. CC-02 y CC-06 dejan la política por serie pendiente de acuerdo y validación. Se propone mostrar error de cálculo ante resultados inválidos para evitar que el tablero presente un riesgo ficticio.
- **Alojamiento.** La elección entre Vercel y servidor separado se cierra en CC-11. CC-12 ejecuta la decisión. CI puede prepararse de forma independiente.

