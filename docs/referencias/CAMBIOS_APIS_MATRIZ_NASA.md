# Cambios de APIs por Variable de Estado (Páginas 7–8)

## Variable: $T_{i,j}(t)$ — Temperatura del Dosel

### PRISM
* **Por qué se cambia:**
  * Cobertura geográfica limitada únicamente a los Estados Unidos contiguos (CONUS).
  * No provee datos climáticos para parcelas ubicadas fuera de EE. UU.
* **API / Dataset de reemplazo:** **ERA5-Land (Copernicus / ECMWF)** o **WorldClim** (como complemento de **NASA POWER** y **SRTM**).

---

## Variable: $W_{i,j}(t)$ — Humedad Radicular

### OpenET
* **Por qué se cambia:**
  * Cobertura restringida únicamente a los 48 estados contiguos de EE. UU.
  * No entrega datos de evapotranspiración fuera de territorio estadounidense.
* **API / Dataset de reemplazo:** **ECOSTRESS ET** (global a ~70 m) / **MODIS MOD16A2** (global a 500 m), o cálculo interno mediante **Penman-Monteith** usando datos de **NASA POWER** / **ERA5-Land**.

### NLDAS
* **Por qué se cambia:**
  * Cobertura limitada a América del Norte central ($25^\circ\text{N}$ a $53^\circ\text{N}$: EE. UU., sur de Canadá y norte de México).
  * No cubre América del Sur ni el resto del mundo.
* **API / Dataset de reemplazo:** **GLDAS (NASA Global Land Data Assimilation System)** o **ERA5-Land** (cobertura global).

### GRACE / GRACE-FO
* **Por qué se cambia:**
  * Resolución espacial nativa demasiado gruesa (~300 km; ~25–30 km en productos asimilados), incompatible con la escala de una parcela agrícola individual.
  * Mide almacenamiento total de agua en toda la columna (incluyendo acuíferos profundos), no humedad radicular directa a nivel de lote.
* **API / Dataset de reemplazo:** **SMAP L4** (humedad radicular global a ~9 km) combinado con **Sentinel-1 SAR** (humedad superficial a ~10–20 m) y **CHIRPS** (precipitación global a ~5 km).

---

## Variable: $\mathbf{N}_{i,j}(t) = [N, P, K]^T$ — Vector de Nutrientes

### SSURGO / WSS
* **Por qué se cambia:**
  * Cobertura exclusiva para Estados Unidos y sus territorios asociados.
  * No contiene propiedades edáficas (OM, CIC, pH, EC) fuera de EE. UU.
* **API / Dataset de reemplazo:** **SoilGrids 2.0 (ISRIC)** (propiedades del suelo globales a 250 m vía API/WCS) junto con **FAO HWSD v2.0 / GAEZ**.

### USGS NWIS
* **Por qué se cambia:**
  * Es un sistema hidrológico de agua (caudales, niveles freáticos y nutrientes disueltos en ríos o pozos), no una base de datos de nutrientes ni química de suelos agrícolas.
  * Cobertura limitada exclusivamente a Estados Unidos.
* **API / Dataset de reemplazo:** **SoilGrids 2.0** + **FAO HWSD v2.0** para propiedades basales del suelo.

### CDL (CropScape)
* **Por qué se cambia:**
  * Cobertura exclusiva para los Estados Unidos contiguos (CONUS).
  * No ofrece mapas históricos de cultivos previos para inferir fijación de nitrógeno fuera de EE. UU.
* **API / Dataset de reemplazo:** **ESA WorldCereal** (cobertura global de cultivos a 10 m) y/o **historial ingresado por el agricultor**.

### Sentinel-2 (Red-Edge) [para estimación directa de P y K]
* **Por qué se cambia:**
  * El Fósforo ($P$) y el Potasio ($K$) no tienen firmas espectrales de absorción directas en el rango óptico/Red-Edge de Sentinel-2.
  * Las bandas Red-Edge detectan clorofila y vigor (proxy de Nitrógeno y estrés general), pero no permiten aislar ni cuantificar por separado deficiencias de $P$, $K$, estrés hídrico o plagas.
* **API / Dataset de reemplazo:** Mantener **Sentinel-2 (Red-Edge)** solo como proxy de vigor/Nitrógeno foliar, y reemplazar la estimación de $P$ y $K$ por **SoilGrids 2.0 / FAO HWSD** más **balances estequiométricos de extracción por cultivo** (o análisis de laboratorio in-situ).

---

## Variable: $B_{i,j}(t)$ — Biomasa Vegetal

### GEDI
* **Por qué se cambia:**
  * Está diseñado y calibrado para altura y biomasa de bosques, por lo que subestima cultivos agrícolas anuales de porte bajo y sufre ruido del suelo.
  * Opera mediante huellas discretas (~25 m) separadas por trazas orbitales, sin cobertura espacial continua pared-a-pared ni seguimiento temporal frecuente por parcela.
* **API / Dataset de reemplazo:** **Sentinel-2 (NDVI/EVI/LAI)** + **Landsat** + **Sentinel-1 SAR** (cobertura global continua a 10–30 m).

### NASS QuickStats
* **Por qué se cambia:**
  * Cobertura restringida únicamente a estadísticas agrícolas de Estados Unidos.
  * No contiene rendimientos históricos ni métricas de producción para otros países.
* **API / Dataset de reemplazo:** **FAOSTAT API** (estadísticas globales por país) y/o **estadísticas agrarias nacionales** (p. ej., **MIDAGRI / SIEA** en Perú).

---

## Variable: $H_{i,j}(t)$ — Espesor Capa Fértil

### SSURGO / WSS
* **Por qué se cambia:**
  * Cobertura exclusiva para Estados Unidos y sus territorios asociados.
  * No contiene datos de profundidad de suelo ni erodabilidad fuera de EE. UU.
* **API / Dataset de reemplazo:** **SoilGrids 2.0 (ISRIC)** + **FAO HWSD v2.0** (como insumos junto a **SRTM** y **GPM/IMERG**).

---

## Variable: $q(t) \in \mathcal{Q}$ — Modo de Rotación

### CDL (CropScape)
* **Por qué se cambia:**
  * Cobertura exclusiva para los Estados Unidos contiguos (CONUS).
  * No ofrece mapas históricos de clasificación de cultivos fuera de EE. UU.
* **API / Dataset de reemplazo:** **ESA WorldCereal** (10 m global) y/o **historial ingresado por el agricultor** combinado con series temporales de **Sentinel-2** para detectar periodos de suelo desnudo.

### USDA AMS Market News
* **Por qué se cambia:**
  * Provee precios mayoristas y volúmenes únicamente para mercados de Estados Unidos.
  * No refleja precios ni idoneidad de mercado local fuera de EE. UU.
* **API / Dataset de reemplazo:** **FAOSTAT Prices API** y/o **fuentes nacionales de precios agrícolas** (p. ej., **SISAP / MIDAGRI** en Perú).

### Ag Data Commons
* **Por qué se cambia:**
  * Es un catálogo/repositorio de archivos de investigación heterogéneos (CSV, ZIP, etc.), no una API uniforme que devuelva parámetros fisiológicos, reglas de rotación o datos de mercado listos para consultar.
  * Está orientado a conjuntos de datos del USDA en EE. UU.
* **API / Dataset de reemplazo:** **FAO EcoCrop / FAO Crop Calendar** y un **catálogo local estructurado** basado en parámetros agronómicos estándar (p. ej., tablas **FAO-56**).
