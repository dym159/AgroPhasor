# Crop Rotation Data for Peru

The [expanded 60-crop inventory](inventario-60-cultivos-peru.md) compiles costs, yields, available farm-gate prices, and cultivar profiles.

Reviewed November 15, 2026. AgroPhasor geographic scope: all 24 departments of Peru and Callao. The active catalog models potato, amylaceous maize, and dry bean (alongside core parameterized strawberry and fallow transition). The collected evidence also supports evaluating rice and cassava as candidates to broaden coverage. Every figure preserves the geographic scope and units of its original source.

## Calendars and Yield

| Crop or cultivar | Source scope | Cycle | Planting & harvest | Reference yield |
| --- | --- | --- | --- | --- |
| Potato (all varieties combined) | Lima, Huánuco, Ayacucho, and Junín | Lima 5 months; Huánuco & Ayacucho 6; Junín 7. Statistical lags between planting and harvest. | MIDAGRI publishes monthly profiles for these departments. In the report's national series, 83.6% of plantings occurred between July and December. | Use regional yield from agricultural statistics. [MIDAGRI, Tables 2–7](https://cdn.www.gob.pe/uploads/document/file/1741892/Observatorio%20de%20las%20siembras%20y%20perspectivas%20de%20la%20producci%C3%B3n%20de%20papa.pdf) |
| Potato INIA 303 Canchán | Central Highlands and Central Coast, per release sheet | 120-day vegetative period | Harvest at physiological maturity. | Up to 30 t/ha reported in farmer fields and 40–50 t/ha under experimental conditions. [INIA 303 Sheet](https://www.inia.gob.pe/wp-content/uploads/investigacion/programa/sistProductivo/variedad/papa/INIA_303.pdf) |
| Amylaceous Maize (all varieties combined) | Ayacucho, Huancavelica, Apurímac, Cusco, Huánuco, Junín, La Libertad, and Piura | Ayacucho & Huancavelica 7 months; Apurímac, Cusco, Huánuco, Junín, La Libertad & Piura 8. Statistical lags. | The report provides regional historical profiles. About 88% of national plantings occur between August and December. Piura concentrates 95% between November and April. | In 2020, the report recorded a national yield of 1.6 t/ha. [MIDAGRI, Table 3 & Chapters II–III](https://cdn.www.gob.pe/uploads/document/file/2639429/Observatorio%20de%20las%20siembras%20y%20perspectivas%20de%20la%20producci%C3%B3n%20de%20%20ma%C3%ADz%20amil%C3%A1ceo%20-%20II%20Cuatrimestre.pdf) |
| Maize INIA 618 Blanco Quispicanchi | Cusco | 240–255 days to maturity | Duration refers to physiological maturity for this cultivar. Preserve the distinction between maturity, harvest, and commercial drying. | Use one comparable observation per cultivar and locality. [INIA 618 Sheet](https://www.inia.gob.pe/wp-content/uploads/investigacion/programa/sistProductivo/variedad/maiz/INIA_618.pdf) |
| Dry Bean INIA 425 Martín Cusco | Inter-Andean valleys of Ayacucho, Cusco, and Apurímac; 2,200–2,900 m | 120 days | Planting September–January; harvest January–May. | Average 1.5–2 t/ha, potential 2.8 t/ha. [INIA Compendium, pp. 188–189](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content#page=188) · [INIA 425 Sheet](https://repositorio.inia.gob.pe/bitstreams/f4775a2c-1dde-4178-88f7-03361864b6c6/download) |
| Dry Bean INIA 439 Costacen | Piura, Lambayeque, La Libertad, Arequipa, Moquegua, and Lima; 400–1,300 m | 90–125 days | Planting May–June; harvest September–October. | Link to the commercial product "dry bean" ("frijol grano seco") before associating prices. [INIA Compendium, pp. 182–183](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content#page=182) |
| Dry Bean INIA 426 Perla Cusco | Cultivar datasheet | 121–128 days | Planting September–January; harvest January–May. | Average 1.5–1.8 t/ha, potential 2.4 t/ha. [INIA Compendium, pp. 186–187](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content#page=186) |
| Cassava | Amazonas, Junín, Ucayali, San Martín, and Loreto | MIDAGRI estimates 8 months in Amazonas, 12 in Junín, 9 in Ucayali, and 6 in San Martín. In Loreto, second-semester plantings correspond to harvests in the same semester of the following year. | Observed concentrations: August–December in Amazonas & Junín, August–October in Ucayali, January–April in San Martín, and July–December in Loreto. | Annex 1 contains planted area series and the report analyzes regional variation. [MIDAGRI, Tables 3–8 & Annex 1](https://cdn.www.gob.pe/uploads/document/file/6064998/4344772-observatorio-de-siembras-y-perspectivas-de-produccion-yuca.pdf?v=1712843397) |
| Paddy Rice | Coast and Amazon (Selva) | 4–5 months depending on zone, with ~4.5-month national average in the observatory. | Reports irrigated production on the Coast, mixed irrigated/rainfed in San Martín, and rainfed in Loreto & Ucayali. Includes profiles of major producing zones. | Extract production by natural region or department and cross-check against harvested area in the same period. [MIDAGRI, Ch. 2](https://cdn.www.gob.pe/uploads/document/file/5930905/3674534-observatorio-de-siembras-y-perspectivas-de-produccion-arroz.pdf?v=1708725598) |

The cultivar compendium is the reference cycle source whenever the cultivar is identified and matches the zone. Statistical lags summarize regional campaigns and support estimating harvest months under uncertainty. Historical planting concentrations provide evidence of local practice. Defining feasible planting dates also requires checking irrigation, elevation, climate, and—in floodplains—river levels. [SENAMHI Agroclimatic Risk](https://www.senamhi.gob.pe/?p=riesgo-agro) · [Amazon Crop Monitoring](https://www.gob.pe/institucion/senamhi/noticias/1399056-senamhi-informa-sobre-avances-diferenciados-en-el-desarrollo-de-cultivos-en-la-amazonia)

## SIEA Series to Import

The following table numbers correspond to the January 2025 bulletin. When importing another edition, verify the header and period of each table.

| Variable | Reviewed tables | Granularity & unit |
| --- | --- | --- |
| Executed plantings | T.13 & T.14 | Region, crop, and season or month, in ha. |
| Harvested area | T.16 & T.17 | Supports seasonal comparison. T.16 gives regional breakdown; T.17 gives national monthly breakdown by crop, in ha. |
| Production | T.18 & T.19 | T.18 gives regional breakdown; T.19 gives national monthly breakdown, in tonnes. |
| Yield | T.20 | Transitory crops by region, in kg/ha. |
| Farm-gate price paid to producer | T.52 & T.53 | T.52 provides the national monthly series by crop; T.53 provides prices by region and product. For a monthly regional series, extract each edition's monthly slice in S/ per kg. |

[January 2025 SIEA Bulletin](https://siea.midagri.gob.pe/portal/phocadownload/datos_estadisticas/mensual/Agro/2025/Agroen_cifras_01_2025.pdf) · [2025 Bulletins & Annexes](https://www.gob.pe/institucion/midagri/informes-publicaciones/6573082-boletin-estadistico-me) · [2026 Bulletins & Annexes](https://www.gob.pe/institucion/midagri/informes-publicaciones/7910469-boletin-estadistico-mensual-el-agro-en-cifras-2026) · [Downloadable Statistical Yearbooks](https://www.gob.pe/institucion/midagri/informes-publicaciones/2730325-compendio-anual-de-produccion-agricola)

### Coverage of the Current CSV

The repository CSV contains 63 rows across the three core active market products. Each row stores crop name, zone, and PEN soles per kg. A per-row month or campaign column is not yet included. "Lima" and "Lima Metropolitana" appear as separate zone labels in the file, and Callao requires mapping verification against published statistical units before assigning price data.

| Official product | Zones in file | Missing within the file's zone set |
| --- | ---: | --- |
| Papa (Potato) | 20 | Loreto, Madre de Dios, San Martín, Tumbes, and Ucayali |
| Maíz amiláceo (Amylaceous Maize) | 20 | Loreto, Madre de Dios, San Martín, Tumbes, and Ucayali |
| Frijol grano seco (Dry Bean) | 23 | Moquegua and Tacna |

[Project CSV](../backend/data/precios_chacra_midagri_2025_2026.csv)

## Observed Costs and Coverage

ENA 2018 serves as the historical baseline. Its costs are reported in nominal PEN soles of the survey year per harvested hectare. The 2026 ESCO annexes provide crop- and region-specific coverage; publication of the ESCO annexes was verified, though individual line-item amounts were not transcribed in this review.

| Crop | Verified historical costs & yields | Recent source identified |
| --- | --- | --- |
| Potato | ENA 2018, national average of S/ 10,405.50/ha. | ESCO for white potato in Huánuco and Ayacucho. |
| Amylaceous Maize | ENA 2018, national average of S/ 1,421.20/ha. Cusco S/ 3,248.02/ha; Apurímac S/ 963.45/ha. | ESCO for Cusco and Apurímac. |
| Dry Bean | ENA 2018, national average of S/ 1,281.60/ha. Coast S/ 1,531.01/ha & 1,510 kg/ha; Highlands S/ 876.92/ha & 1,081 kg/ha; Amazon S/ 462.16/ha & 979 kg/ha. | Reviewed published ESCO annexes do not include dry bean. |
| Rice | ENA 2018, Coast S/ 6,257.51/ha; Highlands S/ 5,512.91/ha; Amazon S/ 2,207.59/ha. | ESCO for Piura and San Martín. |
| Cassava | ENA 2018, Section 8.1.13, available to recover item-level historical cost breakdowns. | Reviewed published ESCO annexes do not include cassava. |

[INEI ENA 2018, Sections 8.1.1, 8.1.2, 8.1.13, 8.1.16 & 8.1.25](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf) · [ESCO Annexes](https://www.gob.pe/institucion/uegps/informes-publicaciones/8096722-encuestas-de-costos-de-produccion-esco) · [MIDAGRI Input, Service & Wage Prices](https://www.gob.pe/institucion/midagri/informes-publicaciones/2730440-compendio-anual-de-insumos-y-servicios-agropecuarios)

## Usage in AgroPhasor and Pending Data

1. Record location, water regime, crop, and cultivar per parcel and phase. Preserve the original cycle value, unit, source, and milestone definition (physiological maturity, harvest, and market sale may occur on separate dates).
2. Compute the earliest next planting date after harvest and soil preparation. Search from that date for a supported regional planting window for the zone and crop, rolling into the next year when necessary. Keep historical national planting concentrations separate from cultivar-verified regional windows.
3. Compare economic margins using matching commercial product, unit, currency, and period. When yield is in t/ha and price is in S/ per kg, revenue in S/ per ha equals yield * 1,000 * price. Subtract per-hectare base cost and add separate irrigation cost only when not already included in base costs. The current optimizer endpoint operates in USD/t and USD/ha. [Recommender Contract](../backend/rotation/README.md)
4. Validate simulated yields against SIEA observations in comparable regions and seasons. Distinguish experimental yield, cultivar sheet potential, and observed farm average. Field-scale calibration of the nutrient model remains pending.
5. Remaining data work includes importing the complete monthly regional price and yield series, transcribing updated ESCO cost figures, and filling missing local windows and cultivars. Source coverage spans Coast, Highlands, and Amazon regions; actual feasibility must still be verified at parcel scale.
