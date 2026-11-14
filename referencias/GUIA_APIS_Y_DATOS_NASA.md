# Guía Maestra de APIs, Datos Satelitales y Mapa (NASA Space Apps)
> **Proyecto:** AgroPhasor — *Adapting Farms with NASA Data*  
> **Propósito:** Plan consolidado de fuentes de datos de la NASA, arquitectura matemática acordada por el equipo, limpieza de datos e integración en el mapa interactivo (Leaflet).

---

## 1. Resumen de lo Acordado por el Equipo (Reunión de Planificación)

A partir de la revisión técnica del equipo, el flujo central de **AgroPhasor** se basa en:

1. **Cero APIs climáticas comerciales cerradas (como OpenWeather):** Para cumplir al 100% los criterios de evaluación de la NASA, el motor se alimenta de bases de datos oficiales de la NASA.
2. **Simulador de Línea de Tiempo a Futuro (1 a 3 años):** Como ningún pronóstico meteorológico tradicional predice el día exacto a un año vista, se modela el **Forzamiento Climatológico** descargando **20 a 30 años de datos históricos diarios de NASA POWER** para la coordenada de la parcela:
   $$F_{\text{futuro}}(t) = \text{Estacionalidad (Series de Fourier / FFT)} + \text{Tendencia Climática Lineal} + \text{Ruido Estocástico (Montecarlo)}$$
3. **Motor Físico de 3 Variables (Temperatura, Humedad del Suelo y Nutrientes) y Visualización por "Escudos":**
   * Las ecuaciones diferenciales (EDOs) evalúan el aguante de la planta frente al clima y se traducen visualmente en una **malla de "Escudos" sobre las sub-parcelas del campo** (celeste = resistente/óptimo, rojo = en riesgo de colapso) a lo largo de una línea de tiempo mensual (*Enero, Febrero...*), acompañada de las curvas de las 3 variables. *(Nota: La Curva de Lissajous aparecía en la guía previa del 5 de nov, pero en la reunión del 8 de nov se reemplazó visualmente por el sistema de **Escudos** por ser mucho más intuitivo para el agricultor).*
   * **Parámetros editables por el agricultor:** El usuario puede ajustar condiciones/imprevistos (tipo de suelo, variaciones de temperatura, lluvia o estación) y ver cómo cambia el escudo y la evolución del campo.
4. **Recomendador de Rotación de Cultivos (Grafos / A\*) Explicable:**
   * El algoritmo busca la ruta de rotación de cultivos que **mantenga los escudos celestes durante todo el año**, y el dashboard **explica el porqué** de cada opción recomendada.
5. **Mapa de Parcelas y Alertas de Riesgo:**
   * Visualización del terreno dividido en sectores/lotes con niveles de riesgo ("escudos" / zonas rojas de estrés) y posibilidad de alerta en campo (ej. vibración en el navegador móvil con `navigator.vibrate` al entrar en una zona crítica).

---

## 2. Clasificación Oficial de Recursos de la NASA (Qué Usar y Qué Descartar)

### Prioridad 1: Columna Vertebral (Obligatorio — Backend y Modelo Físico)

| Recurso | Rol en AgroPhasor | ¿Requiere Cuenta / API Key? | Estado y Cobertura |
| :--- | :--- | :--- | :--- |
| **NASA POWER API** *(Agroclimatology)* | Fuente principal de series históricas diarias (20–30 años) de Temperatura, Radiación, Lluvia y Humedad del suelo para la FFT y las EDOs. | **No** (100% pública y directa en JSON). | **Verificada en vivo.** Cobertura global (incluye todo el Perú). |
| **Parámetros FAO-56 / FAO GAEZ** | Coeficientes de cultivo ($K_c$), umbrales térmicos/hídricos y reglas agronómicas para el algoritmo **A\*** de rotación. | **No** (tablas/parámetros en el motor). | Cobertura global (aplicable a cultivos andinos y costeros). |

### Prioridad 2: Respaldo Satelital Directo (Recomendado para Puntaje Extra)

| Recurso | Rol en AgroPhasor | ¿Requiere Cuenta? | Cómo usarlo sin perder tiempo |
| :--- | :--- | :--- | :--- |
| **SMAP** *(Soil Moisture Active Passive)* | Validación satelital directa de humedad superficial (`SPL3SMP`) y de zona radicular (`SPL4SMGP`). | **Sí:** Cuenta gratuita de **NASA Earthdata Login** (`urs.earthdata.nasa.gov`). | Descargar previamente con `earthaccess` una muestra real de la zona de estudio (Mantaro/Ica) o usar `GWETTOP`/`GWETROOT` ya asimilados en NASA POWER. |
| **SRTM** *(Elevación y Terreno)* | Altitud y pendiente del lote para ajustar riesgo de heladas y escorrentía superficial. | Sí (Earthdata) o consulta puntual de elevación. | Usar la altitud real del lote (ej. ~3250 m s. n. m. en Mantaro) como parámetro fijo/contextual del modelo. |

### Prioridad 3: 100% Opcional (Solo si alcanza el tiempo al final)

> [!TIP]
> **El único escenario donde sirven IMERG (GPM), MODIS/VIIRS o Landsat en un hackathon de 36 horas:**
> **Solo como capa visual en Leaflet (vía NASA GIBS).** No descargues ni proceses sus archivos crudos `.h5` o NetCDF en el backend; simplemente agrega su URL de teselas (tiles WMTS/XYZ) como una capa superpuesta sobre el mapa satelital para mostrar **lluvia (IMERG)** o **vegetación (NDVI de MODIS/VIIRS)** de forma visual si sobra tiempo al final.

### Recursos Descartados (No usar para el caso de estudio en Perú)

> [!WARNING]
> **Evitar pérdida de tiempo en el hackathon:** Los siguientes recursos de la lista oficial del desafío **no sirven** para nuestro caso de estudio en Perú o no aplican al modelo:

1. **Exclusivos de EE. UU. / Norteamérica (Vacíos en Perú):**
   * *Web Soil Survey (WSS)* y *USDA NRCS SSURGO / STATSGO2*
   * *Cropland Data Layer (CDL) / CropScape*
   * *PRISM Climate Data*
   * *National Agriculture Imagery Program (NAIP)*
   * *USGS National Land Cover Database (NLCD)* y *USFS LANDFIRE*
   * *CoCoRaHS* y *USGS National Water Information Systems (NWIS)*
   * *USDA AMS Market News* y *USDA NASS QuickStats*
   * *OpenET*
2. **No aplicables al problema agronómico o demasiado pesados en crudo:**
   * *GEDI:* Mide estructura vertical y biomasa de bosques altos, no cultivos agrícolas de rotación.
   * *NISAR L0B (`RRSD` en ASF):* Son señales de radar crudas sin enfocar (archivos `.h5` gigantes pensados para procesadores SAR como `isce3`). No son necesarios teniendo **NASA POWER** y **SMAP**.

---

## 3. Guía Técnica de Integración: API de NASA POWER (Verificada)

### Endpoint REST Oficial (Sin API Key)

```text
https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN,RH2M,GWETTOP,GWETROOT&community=AG&longitude=-75.21&latitude=-12.06&start=20060101&end=20261110&format=JSON
```

### Variables Clave Devueltas en `properties.parameter`

| Código en la API | Variable Física / Agronómica | Unidad | Uso en AgroPhasor |
| :--- | :--- | :--- | :--- |
| `T2M` | Temperatura media a 2 metros | °C | Serie base para FFT, eje X de **Lissajous** y EDO térmica. |
| `T2M_MIN` / `T2M_MAX` | Temperatura mínima y máxima diaria | °C | Detección de riesgo de heladas (`T2M_MIN < 2 °C`) o estrés por calor. |
| `PRECTOTCORR` | Precipitación diaria corregida | mm/día | Entrada de agua por lluvia en la EDO de balance hídrico. |
| `ALLSKY_SFC_SW_DWN` | Radiación solar incidente en superficie | $\text{MJ/m}^2/\text{día}$ | Forzamiento radiativo ($f_{\text{rad}}$) y cálculo de evapotranspiración. |
| `RH2M` | Humedad relativa a 2 metros | % | Contexto atmosférico y riesgo de plagas/hongos. |
| `GWETTOP` | Humedad del suelo superficial (0–5 cm) | Fracción (0 a 1) | Condición inicial y validación del estado superficial. |
| `GWETROOT` | Humedad en zona radicular (0–100 cm) | Fracción (0 a 1) | Eje Y de la **Curva de Lissajous** y estado hídrico para rotación. |

### Reglas Críticas para el Backend en Python (Detectadas en Pruebas Reales)

1. **Limpieza obligatoria de valores `-999.0` antes de la FFT:**
   * NASA POWER marca los días aún no procesados (los últimos **2 a 3 días** respecto a la fecha actual) y eventuales huecos de sensores con el valor `-999.0`.
   * **Regla:** Antes de calcular la Transformada Rápida de Fourier (`numpy.fft.rfft`) o la pendiente lineal, reemplazar cualquier valor `<= -900` mediante interpolación lineal (o el promedio del mismo día del año) y recortar los últimos días en `-999.0`. Si entra un `-999.0` a la FFT, distorsiona todas las frecuencias.
2. **Caché Local (`mock_nasa_data.json`):**
   * Una petición de 20 años diarios pesa ~2.7 MB y tarda ~5–6 segundos.
   * Guardar en disco las respuestas de las zonas de demostración (ej. **Valle del Mantaro** `-12.06, -75.21` y **Valle de Ica** `-14.07, -75.73`) permite que los sliders del simulador re-ejecuten las EDOs en menos de 50 ms y protege la demo ante caídas de red.

---

## 4. Arquitectura en Leaflet: Mapa Base + Capas NASA GIBS (Opcional)

### 4.1. Configuración Base (Obligatoria y Rápida)
Usar **Leaflet.js** con la capa satelital gratuita de **Esri World Imagery** (no pide API key ni tarjeta) y dibujar encima los polígonos de la parcela coloreados según el nivel de estrés calculado por el motor físico:

```javascript
// 1. Inicializar mapa centrado en el Valle del Mantaro (o coordenadas buscadas)
const map = L.map('map').setView([-12.06, -75.21], 14);

// 2. Capa base satelital de alta resolución (Esri World Imagery - sin API key)
const esriSat = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {
    maxZoom: 19,
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics'
  }
).addTo(map);
```

### 4.2. Escenario Opcional (Solo si sobra tiempo al final): Capas Visuales con NASA GIBS
Si al final del domingo sobra tiempo y quieren agregar un selector de capas satelitales oficiales de la NASA en el mapa **sin descargar ni procesar datos en el backend**, basta con añadir estas URLs de **NASA GIBS** con opacidad `0.5`–`0.6`:

```javascript
// OPCIONAL: Capa visual de Vegetación (MODIS NDVI - 8 días) vía NASA GIBS
const nasaModisNDVI = L.tileLayer(
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_NDVI_8Day/default/2026-10-16/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png',
  {
    maxZoom: 9,
    opacity: 0.55,
    attribution: 'NASA EOSDIS GIBS (MODIS NDVI)'
  }
);

// OPCIONAL: Capa visual de Precipitación (GPM IMERG) vía NASA GIBS
const nasaImergPrecip = L.tileLayer(
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate/default/2026-11-01/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png',
  {
    maxZoom: 6,
    opacity: 0.55,
    attribution: 'NASA EOSDIS GIBS (GPM IMERG)'
  }
);

// Control de capas en la esquina del mapa (solo si se activa este extra)
L.control.layers(
  { 'Satélite Base (Esri)': esriSat },
  {
    'NASA MODIS NDVI (Vegetación)': nasaModisNDVI,
    'NASA IMERG (Precipitación)': nasaImergPrecip
  }
).addTo(map);
```

> [!NOTE]
> Como las capas de GIBS tienen resolución regional (`maxZoom` 6 a 9), funcionan mejor al alejar un poco el zoom para mostrar el contexto climático del valle, mientras que a nivel de parcela individual (`zoom` 14–18) manda el polígono interactivo de **AgroPhasor** alimentado por **NASA POWER + EDOs**.

---

## 5. Cuenta NASA Earthdata Login (Para SMAP / `earthaccess`)

Si deciden descargar un archivo real de **SMAP** para mostrar validación satelital directa:

1. **Credenciales:** Se usa la cuenta de **NASA Earthdata Login** (`https://urs.earthdata.nasa.gov/`), que es independiente de la cuenta de `spaceappschallenge.org`.
   * *Recordatorio:* En el login se ingresa el **Username** (nombre de usuario), no el correo electrónico.
2. **Archivo `.netrc` (opcional para no escribir contraseñas en código):**
   Crear `C:\Users\<tu_usuario>\.netrc` con:
   ```text
   machine urs.earthdata.nasa.gov
   login TU_USERNAME_EARTHDATA
   password TU_PASSWORD_EARTHDATA
   ```
3. **Consulta rápida de SMAP en Python con `earthaccess`:**
   ```python
   import earthaccess

   earthaccess.login()  # Usa .netrc o pide usuario/contraseña
   results = earthaccess.search_data(
       short_name="SPL3SMP_E",  # SMAP L3 Humedad del Suelo 9 km
       temporal=("2026-10-01", "2026-11-10"),
       bounding_box=(-75.5, -12.3, -75.0, -11.8)  # Valle del Mantaro
   )
   ```

---

## 6. Restricciones de Seguridad ("Parachoques" entre la Web y el Motor Físico)

Para integrar las ecuaciones del equipo de Física sin riesgo de que un cálculo extremo (`NaN`, división por cero o valores fuera de escala) rompa la interfaz web, el código aplica únicamente **dos restricciones de validación** sin modificar las fórmulas internas de los físicos:

### 6.1. Restricción de Entrada (Limpiar `-999.0` de NASA POWER antes de pasar los datos)
```python
def limpiar_serie_nasa(diccionario_fechas, valor_por_defecto=15.0):
    """
    Reemplaza los -999.0 de la NASA por el último valor válido conocido
    para que las ecuaciones diferenciales y la FFT nunca reciban datos corruptos.
    """
    serie_limpia = {}
    ultimo_valido = valor_por_defecto

    for fecha, valor in diccionario_fechas.items():
        if valor is not None and valor > -900:
            ultimo_valido = float(valor)
        serie_limpia[fecha] = ultimo_valido

    return serie_limpia
```

### 6.2. Restricción de Salida (Topes `0` a `100` y filtro anti-`NaN`)
```python
import math

def asegurar_rango(valor, minimo=0.0, maximo=100.0, respaldo=50.0):
    """
    Garantiza que el resultado de cualquier ecuación (ej. Escudo, Humedad, Nutrientes)
    esté siempre entre [minimo, maximo] y nunca sea NaN ni Infinito.
    """
    try:
        v = float(valor)
        if math.isnan(v) or math.isinf(v):
            return respaldo
        return max(minimo, min(maximo, v))
    except (TypeError, ValueError):
        return respaldo
```

*(En el frontend JavaScript se puede aplicar el mismo seguro en una línea: `const escudoSeguro = Math.min(100, Math.max(0, Number.isFinite(val) ? val : 50));`).*

---

## 7. Orden de Ejecución Recomendado (Prioridades para el Fin de Semana)

1. **Fase 1 (Core de Datos — Sábado AM):**
   * Conectar el endpoint de **NASA POWER API** para extraer los 20 años diarios (`T2M`, `PRECTOTCORR`, `ALLSKY_SFC_SW_DWN`, `GWETROOT`), pasarlos por `limpiar_serie_nasa()` y guardar el JSON de respaldo local.
2. **Fase 2 (Motor Matemático — Sábado PM):**
   * Integrar el módulo de los físicos (**Fourier + EDOs + Grafos/A\***) envolviendo sus salidas con `asegurar_rango()` y asegurando que devuelva las opciones de rotación con su explicación.
3. **Fase 3 (Dashboard e Interacción — Sábado Noche / Domingo AM):**
   * Mapa **Leaflet** con lotes/polígonos coloreados por el nivel del **Escudo** (celeste vs. rojo), las 3 curvas de evolución (`Temperatura`, `Humedad`, `Nutrientes`), tarjetas de rotación explicadas y controles para que el agricultor edite parámetros en vivo.
4. **Fase 4 (Extras Opcionales — Domingo PM, solo si todo lo anterior ya está listo):**
   * Agregar el control `L.control.layers` con las capas visuales de **NASA GIBS** (IMERG / MODIS NDVI) en Leaflet.
   * Modo en movimiento / alerta con vibración al entrar en zonas rojas y asistente de consultas (Chatbot).
