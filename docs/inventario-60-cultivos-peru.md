# 60-Crop Inventory for Crop Rotations in Peru

This inventory covers 60 crop groups and retains 71 product or cultivar records. Separate market presentations of maize, sugarcane, barley, pea, fava bean, and chili/sweet peppers remain visible within their groups so figures can be compared without double-counting them as distinct botanical crops. Rocoto is kept as its own group. Selection prioritizes transitory species, roots/tubers, vegetables, and forages across all 24 departments of Peru and Callao, with source-specific geographic coverage.

## Prioritization for AgroPhasor

Inclusion criteria require documented Peruvian cultivation, with figures grounded in Peruvian production statistics, parcels, or field trials. Prioritization follows official ministry focus, value for botanical-family alternation, and coverage across Coast, Highlands, and Amazon zones.

| Priority | Crops & products | Selection rationale |
| --- | --- | --- |
| First integration tier | Potato, rice, hard yellow maize, amylaceous maize, fresh cob maize (choclo), quinoa, cassava, and dry bean. | The first seven anchor the 2025/2026 Crop Guidance Framework (33% of national gross agricultural production value). Dry bean contributes a key legume and ranks among flagship crops in the 2026/2027 National Planting Intentions Survey (ENIS). [MIDAGRI Guidance Framework](https://www.gob.pe/institucion/midagri/noticias/1231067-midagri-area-sembrada-2025-2026-crecera-5-4-en-comparacion-a-ultimas-cinco-campanas-agricolas) · [ENIS Results](https://www.gob.pe/institucion/midagri/noticias/1418927-midagri-proyecta-mas-de-2-millones-de-hectareas-de-siembra-impulsadas-por-maiz-papa-y-frijol) |
| Expanded prioritized transitory crops | Garlic, chili pepper, cotton, green & dry pea, sweet potato, barley, onion, olluco, paprika pepper, rocoto, tomato, wheat, carrot, and squash. | Complete the 23 ENIS 2026/2027 products included in the inventory, prioritized by output, planted area, and food-security importance. [Official ENIS List](https://www.gob.pe/institucion/midagri/noticias/1386511-midagri-inicia-la-encuesta-nacional-de-intenciones-de-siembra-para-la-campana-agricola-2026-2027) |
| Zonal rotation complements | Fava bean, tarwi (Andean lupin), and vetch in the Highlands; cowpea on the Northern Coast, per cultivar sheets. | Provide botanical-family rotation alternatives under suitable local conditions; planting windows and cycle durations are verified per cultivar and department. |
| High-value multi-year or perennial crops | Coffee, cacao, avocado, table/wine grape, olive, blueberry, banana/plantain, and oil palm. | Major national production crops; recommending them in multi-season rotations requires representing establishment, multi-year occupancy, or successive harvests. [2025 Agricultural Balance](https://www.gob.pe/institucion/midagri/noticias/1347928-midagri-sector-agropecuario-alcanzo-un-crecimiento-de-4-8-al-cierre-del-ano-2025) · [2026 Agricultural Output](https://www.gob.pe/institucion/midagri/noticias/1428237-midagri-sector-agropecuario-experimento-crecimiento-de-1-2-en-primer-semestre-del-ano) |

Beyond the 23 ENIS transitory staples, the 60-group inventory documents complementary rotation options and long-cycle systems. Recent economic weight by product can be checked in the [MIDAGRI Monthly Gross Agricultural Value Report](https://www.gob.pe/institucion/midagri/informes-publicaciones/7800032-informe-mensual-del-valor-bruto-de-la-produccion-agropecuaria-2026).

## Available Costs, Yields, and Prices

- **ENA Cost and Yield** correspond to **2018** historical national estimates, expressed in nominal PEN soles per harvested hectare (`S/ per ha`) and `kg/ha` when an explicit chapter average is published.
- **Project Farm-Gate Price** shows the min–max range across zones in the [existing CSV](../backend/data/precios_chacra_midagri_2025_2026.csv). Because the CSV lacks per-row dates, these ranges characterize the file rather than being paired directly with 2018 costs to compute current net margin.
- **—** indicates that no verified comparable figure is included in this inventory. Commercial presentations are listed separately whenever cost, yield, or price belongs to distinct marketable products.
- **Rotation handling classes:** multi-cut forages and long-cycle/perennial plantations require dedicated land-occupancy rules, while transitory crops still require verifying local planting windows, cultivars, and water regimes before recommendation.

Summary breakdown: **32 transitory crops**, **5 multi-cut or variable-stay forages**, and **23 perennial, long-cycle, or successive-harvest crops**.
Coverage totals: **63 records with historical cost**, **61 with extracted historical yield**, and **47 with reference prices in the project CSV**.

### Transitory Crops

| Crop group | Product | ENA Cost (S/ per ha) | ENA Yield (kg/ha) | CSV Price (S/ per kg) | Source |
| --- | --- | ---: | ---: | ---: | --- |
| Peppers (Capsicum) | Paprika | 15,096.9 | 7,877 | 1.80–12.00 (9 zones) | [ENA, p. 107](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=107) |
| Peppers (Capsicum) | Chili pepper (Ají) | 15,985.3 | 21,511 | 0.36–12.00 (19 zones) | [ENA, p. 141](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=141) |
| Peppers (Capsicum) | Bell/Sweet pepper | 32,838.6 | 34,334 | 1.30–3.20 (8 zones) | [ENA, p. 155](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=155) |
| Peppers (Capsicum) | Piquillo pepper | 30,281.0 | 25,112 | 0.30–2.00 (3 zones) | [ENA, p. 163](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=163) |
| Garlic | Garlic | 9,952.2 | 7,684 | 1.60–10.68 (18 zones) | [ENA, p. 123](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=123) |
| Cotton | Cotton | 5,003.9 | 2,702 | 1.50–7.00 (8 zones) | [ENA, p. 119](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=119) |
| Rice | Rice | 4,723.98 | 8,471 | 0.70–3.38 (16 zones) | [ENA, p. 53](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=53) |
| Pea | Green pea | 2,783.4 | 2,371 | 1.93–4.78 (19 zones) | [ENA, p. 113](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=113) |
| Pea | Dry pea | 641.6 | 565 | 2.19–5.84 (17 zones) | [ENA, p. 137](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=137) |
| Forage Oat | Forage Oat | 1,504.4 | 15,181 | 0.18–0.97 (13 zones) | [ENA, p. 89](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=89) |
| Broccoli | Broccoli | 4,901.5 | 11,084 | — | [ENA, p. 171](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=171) |
| Sweet Potato | Sweet Potato | 3,011.0 | 14,752 | 0.80–2.50 (20 zones) | [ENA, p. 115](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=115) |
| Cañihua | Cañihua | — | — | — | [INIA, p. 398](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Cowpea | Cowpea | — | — | — | [INIA, p. 208](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Barley | Barley (grain) | 1,548.2 | 1,508 | 1.00–3.21 (20 zones) | [ENA, p. 111](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=111) |
| Barley | Forage barley | 7,692.9 | 13,766 | 0.30–1.00 (8 zones) | [ENA, p. 151](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=151) |
| Onion | Onion | 14,925.2 | 54,836 | 0.76–2.00 (19 zones) | [ENA, p. 85](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=85) |
| Dry Bean | Dry Bean | 1,281.6 | 1,363 | 1.98–9.02 (23 zones) | [ENA, p. 101](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=101) |
| Fava Bean | Dry fava bean | 1,261.0 | 1,110 | 1.25–6.00 (18 zones) | [ENA, p. 129](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=129) |
| Fava Bean | Green fava bean | 3,674.2 | 4,288 | — | [ENA, p. 167](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=167) |
| Kiwicha (Amaranth) | Kiwicha | — | — | — | [INIA, p. 390](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Lettuce | Lettuce | 16,568.5 | 11,327 | — | [ENA, p. 181](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=181) |
| Lentil | Lentil | — | — | — | [INIA, p. 248](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Maize | Hard yellow maize | 3,067.2 | 4,657 | 0.82–2.87 (24 zones) | [ENA, p. 63](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=63) |
| Maize | Amylaceous maize | 1,421.2 | 1,302 | 2.08–5.89 (20 zones) | [ENA, p. 83](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=83) |
| Maize | Choclo (fresh cob maize) | 2,772.5 | 9,776 | 0.47–4.19 (21 zones) | [ENA, p. 91](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=91) |
| Maize | Forage maize (chala) | 4,673.5 | 46,769 | 0.26–3.00 (10 zones) | [ENA, p. 105](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=105) |
| Andean Oca | Oca | 5,520.0 | 5,520 | 0.83–3.85 (17 zones) | [ENA, p. 161](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=161) |
| Olluco | Olluco | 4,407.2 | 5,215 | 0.67–3.93 (18 zones) | [ENA, p. 127](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=127) |
| Lima Bean | Dry lima bean (Pallar) | 3,633.3 | 1,845 | 1.04–6.00 (7 zones) | [ENA, p. 189](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=189) |
| Potato | Potato | 10,405.50 | 21,795 | 0.52–12.22 (20 zones) | [ENA, p. 55](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=55) |
| Quinoa | Quinoa | 5,906.2 | 2,630 | 3.00–6.19 (16 zones) | [ENA, p. 125](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=125) |
| Watermelon | Watermelon | 7,744.8 | 25,978 | — | [ENA, p. 173](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=173) |
| Tarwi (Andean Lupin) | Tarwi | — | — | — | [INIA, p. 242](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Tomato | Tomato | 20,077.8 | 123,833 | 0.37–4.00 (22 zones) | [ENA, p. 103](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=103) |
| Wheat | Wheat | 1,290.9 | 1,346 | 0.90–5.50 (20 zones) | [ENA, p. 109](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=109) |
| Triticale | Triticale | — | — | — | [INIA, p. 320](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Vetch | Vetch | — | — | — | [INIA, p. 352](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Cassava | Cassava | 3,713.2 | 12,525 | 0.42–2.94 (23 zones) | [ENA, p. 77](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=77) |
| Carrot | Carrot | 6,830.8 | 26,153 | 0.54–2.50 (19 zones) | [ENA, p. 147](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=147) |
| Squash | Squash | 5,085.0 | 20,608 | 0.49–2.39 (25 zones) | [ENA, p. 135](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=135) |

### Multi-Cut or Variable-Stay Forages

| Crop group | Product | ENA Cost (S/ per ha) | ENA Yield (kg/ha) | CSV Price (S/ per kg) | Source |
| --- | --- | ---: | ---: | ---: | --- |
| Alfalfa | Alfalfa | 3,608.7 | 49,236 | 0.16–1.00 (20 zones) | [ENA, p. 65](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=65) |
| Brachiaria | Brachiaria | 388.5 | 45,537 | — | [ENA, p. 81](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=81) |
| Elephant grass | Elephant grass | 512.9 | 19,583 | — | [ENA, p. 117](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=117) |
| Ryegrass | Ryegrass | 9,624.9 | 73,377 | — | [ENA, p. 149](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=149) |
| Clover | Clover | 1,336.9 | 34,273 | — | [ENA, p. 179](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=179) |

### Perennial, Long-Cycle, or Successive-Harvest Crops

| Crop group | Product | ENA Cost (S/ per ha) | ENA Yield (kg/ha) | CSV Price (S/ per kg) | Source |
| --- | --- | ---: | ---: | ---: | --- |
| Olive | Olive | 6,925.1 | 4,535 | 2.38–8.19 (8 zones) | [ENA, p. 79](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=79) |
| Artichoke | Artichoke | 12,835.4 | 16,381 | 1.60–4.20 (7 zones) | [ENA, p. 93](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=93) |
| Blueberry | Blueberry | 40,754.53 | 6,504 | 7.00–15.00 (8 zones) | [ENA, p. 67](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=67) |
| Cacao | Cacao | 5,671.2 | 1,489 | 6.94–24.11 (16 zones) | [ENA, p. 71](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=71) |
| Coffee | Coffee | 2,130.1 | — | — | [ENA, p. 57](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=57) |
| Camu camu | Camu camu | — | — | — | [INIA, p. 436](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Sugarcane | Sugarcane (sugar) | 6,396.4 | 123,796 | — | [ENA, p. 73](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=73) |
| Sugarcane | Sugarcane (alcohol) | 4,457.3 | 72,303 | — | [ENA, p. 153](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=153) |
| Sugarcane | Sugarcane (ethanol) | 6,067.6 | 123,785 | — | [ENA, p. 159](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=159) |
| Asparagus | Asparagus | 11,017.5 | — | 2.00–7.75 (5 zones) | [ENA, p. 59](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=59) |
| Strawberry | Strawberry | 7,954.1 | 13,283 | — | [ENA, p. 191](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=191) |
| Pomegranate | Pomegranate | 15,827.1 | 16,193 | — | [ENA, p. 175](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=175) |
| Lime / Lemon | Lime (Limón) | 7,412.9 | 19,245 | 0.60–4.64 (24 zones) | [ENA, p. 121](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=121) |
| Mandarin | Mandarin | 10,452.6 | 39,349 | 0.50–3.13 (18 zones) | [ENA, p. 87](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=87) |
| Mango | Mango | 8,244.1 | 19,478 | 0.36–5.24 (23 zones) | [ENA, p. 97](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=97) |
| Passion fruit | Passion fruit (Maracuyá) | 18,761.6 | 11,153 | — | [ENA, p. 177](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=177) |
| Orange | Orange | 5,778.6 | 24,482 | 0.40–2.50 (25 zones) | [ENA, p. 95](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=95) |
| Oregano | Oregano | 3,212.3 | 2,332 | 1.00–12.00 (9 zones) | [ENA, p. 133](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=133) |
| Oil palm | Oil palm | 4,238.5 | 17,698 | 0.46–0.71 (4 zones) | [ENA, p. 194](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=194) |
| Avocado | Avocado (Palta) | 13,373.3 | 13,490 | 0.51–17.18 (24 zones) | [ENA, p. 75](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=75) |
| Papaya | Papaya | 3,940.3 | 11,668 | 0.43–3.80 (23 zones) | [ENA, p. 157](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=157) |
| Pineapple | Pineapple | 5,068.0 | 17,180 | 0.42–2.20 (13 zones) | [ENA, p. 99](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=99) |
| Banana / Plantain | Banana / Plantain | 13,352.2 | 21,760 | 0.44–3.60 (25 zones) | [ENA, p. 69](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=69) |
| Rocoto | Rocoto | 2,102.5 | 8,513 | — | [ENA, p. 165](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=165) |
| Grape | Grape | 52,802.2 | 19,915 | 2.00–5.99 (14 zones) | [ENA, p. 61](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=61) |

## Technically Documented Cycles and Planting Windows

Dates correspond to the indicated cultivars and regions. INIA page numbers refer to printed pages in the compendium. "Pot." denotes potential yield reported on the cultivar datasheet.

| Crop & reference | Documented zone | Cycle & milestone basis | Planting → harvest | Datasheet yield |
| --- | --- | --- | --- | --- |
| Potato Canchán, INIA p. 58 | Junín, Huancavelica, Huánuco, Áncash, and Lima | 120 days | October–December → January–April | — |
| Amylaceous Maize Cumbemaino, INIA p. 116 | Cajamarca and La Libertad | 165–180 days | November–December → April–June | Pot. 4 t/ha |
| Amylaceous Maize Blanco Quispicanchi | Cusco | 240–255 days to maturity | — | [INIA 618 Sheet](https://www.inia.gob.pe/wp-content/uploads/investigacion/programa/sistProductivo/variedad/maiz/INIA_618.pdf) |
| Dry Bean Costacen, INIA p. 182 | Piura, Lambayeque, La Libertad, Arequipa, Moquegua, and Lima | 90–125 days | May–June → September–October | 3.1 t/ha avg |
| Dry Bean Canario Camanejo, INIA p. 184 | Arequipa and Áncash | 150 days | March–June → October–November | 2–2.5 t/ha avg |
| Dry Bean Perla Cusco, INIA p. 186 | Ayacucho, Cusco, and Apurímac | 121–128 days | September–January → January–May | 1.5–1.8 t/ha avg |
| Dry Bean Martín Cusco, INIA p. 188 | Ayacucho, Cusco, and Apurímac | 120 days | September–January → January–May | 1.5–2 t/ha avg |
| Cowpea Vaina Verde, INIA p. 208 | Lambayeque, Piura, Tumbes, and La Libertad | 80–100 days | October–March → January–June | Pot. 3 t/ha |
| Fava Bean Siwina, INIA p. 216 | Apurímac, Puno, Cusco, and Ayacucho | 158 days | September–October → February–March | 2.5–3 t/ha avg |
| Pea Remate, INIA p. 236 | Junín, Cajamarca, Huancavelica, Áncash, and Ayacucho | 150 days | September–December → January–April | — |
| Tarwi Masacanchino, INIA p. 242 | Apurímac, La Libertad, Cajamarca, and Amazonas | 208 days | October–November → May–June | Pot. 1.4–1.66 t/ha |
| Lentil Argentino Precoz, INIA p. 248 | Cajamarca, Piura, Lambayeque, and La Libertad | 120–130 days | Highlands Jan–Feb, Coast Apr–Jul. Verify harvest by zone | 0.8–1 t/ha avg |
| Rice La Unión 23, INIA p. 254 | Cajamarca and Amazonas | 125–140 days | Datasheet lists year-round planting & harvest; apply local water and campaign availability | Pot. 10 t/ha |
| Wheat Antapampino, INIA p. 288 | Highlands (including Cajamarca, Pasco, Junín, Huancavelica, Huánuco) | 125 days | November–December → March–April | Pot. 4.8–5 t/ha |
| Triticale Salkantay, INIA p. 320 | Highlands (including Pasco, Junín, Huancavelica, Huánuco, Ayacucho) | 103 days | March–December → July–April | Pot. 4.66 t/ha grain |
| Barley La Milagrosa, INIA p. 326 | Highlands (including Cajamarca, Pasco, Junín, Huancavelica, Huánuco) | 137 days | November–January → April–June | Pot. 4.5 t/ha |
| Oat Katekyl, INIA p. 334 | Cajamarca, Amazonas, and La Libertad | Forage 90–100 days; seed 180–200 days | October–December → forage Jan–Mar or grain Apr–Jun | — |
| Vetch Caxamarca, INIA p. 352 | Highlands (including Cajamarca, Cusco, Junín, Ayacucho, Pasco) | Forage 95 days; grain 195 days | Forage Nov–Feb → Feb–May; grain May–Jul per sheet | — |
| Ryegrass Kumymarca, INIA p. 358 | Cajamarca | Semi-perennial, 30–45 days to grazing/cutting per sheet | September–October → November–December | — |
| Quinoa Atipaq, INIA p. 364 | Puno | 150–160 days | October–November → March–April | Pot. 3.5–6 t/ha |
| Kiwicha La Frondosa, INIA p. 390 | Puno, Cusco, Ayacucho, Apurímac, and Huancavelica | 150–155 days | November–December → April–June | 2.5 t/ha avg |
| Cañihua Illpa, INIA p. 398 | Puno | 140 days | October–November → February–April | 2.5–3 t/ha avg |
| Cotton Colorina, INIA p. 400 | San Martín | 168 days | December–January → May–June; February–March → July–August | — |
| Sugarcane PVF 03-115, INIA p. 416 | Lambayeque, Piura, and Cajamarca | 18 months | Datasheet records January & July planting, July & November harvest | — |
| Garlic Donajus, INIA p. 422 | Arequipa, Ica, Lima, Huaraz, and Chimbote | 5 months | April–July → September–December | Pot. 17 t/ha |
| Carrot Huaralina Precoz, INIA p. 430 | Lima, Ica, and Junín | Coast 90–110 days; Highlands 110–120 days | Coast Apr–Oct → Aug–Feb; Highlands listed year-round | — |
| Sweet Potato Bondadosa, INIA p. 92 | La Libertad, Piura, Lima, Ica, and Lambayeque | 3.5–4 months | Listed year-round | Pot. 60 t/ha |
| Oca K’eny Rojo, INIA p. 106 | Puno | 190 days | September → April | 24.5 t/ha avg |
| Lima Bean Iqueño Precoz, INIA p. 442 | Ica | 125 days | March–April → July–September | Pot. 0.95 t/ha |
| Camu camu Vitahuayo, INIA p. 436 | Loreto, San Martín, and Ucayali | Requires establishment & perennial horizon data | Year-round planting, November–April harvest per sheet | — |
| Cassava, regional observatory | Amazonas, Junín, Ucayali, and San Martín | Estimated lags of 8, 12, 9, and 6 months respectively | Peak plantings Aug–Dec in Amazonas & Junín, Aug–Oct in Ucayali, Jan–Apr in San Martín | [MIDAGRI Observatory, Tables 5–8](https://cdn.www.gob.pe/uploads/document/file/6064998/4344772-observatorio-de-siembras-y-perspectivas-de-produccion-yuca.pdf?v=1712843397) |
| Olluco, field guide | Andes, depending on elevation and cultivar | 180–220 days to harvest | — | [Andean Crops Field Guide](https://www2.congreso.gob.pe/sicr/cendocbib/con4_uibd.nsf/EA54F80C677EA73C05257D20007700FD/%24FILE/Gu%C3%ADaCampoCultivosAndinos.pdf) |
| Paprika pepper, INIA manual | Paprika manual reference | 120–150 days to harvest maturity | — | [INIA Manual, p. 18](https://repositorio.inia.gob.pe/server/api/core/bitstreams/4023af50-e2e0-45fd-b047-8e3cd142ae66/content) |

[INIA Cultivar Compendium](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) · [Coast Calendar](https://repositorio.inia.gob.pe/items/c5a4c11c-d0c7-41b9-b0bf-fe200c2bf403) · [Highlands Calendar](https://repositorio.inia.gob.pe/items/545185cc-25ea-42d7-b877-60d6e3e24978/full) · [Amazon Calendar](https://repositorio.inia.gob.pe/items/682cd18e-1b10-40b7-b6cc-6a5bc43c25f0)

## Pending Checks Before Activating a Crop

| Recommender requirement | Evidence required |
| --- | --- |
| Chaining planting and harvest | Record botanical family, cultivar, cycle milestone definition, feasible months, zone, and irrigation regime. Adapt horizon rules for multi-cut crops and perennial plantations. |
| Comparing yields | Match observations to the exact commercial product and regional scope. Datasheet potentials serve as simulator reference bounds and must keep their label. |
| Computing margin | Pair price for the same product and month with recent regional costs in identical currency. Cross-check extreme CSV values against source tables and units before activation. |
| Covering a data-sparse zone | Confirm whether the department or Callao has an independent observation; prompt the user for local values whenever sources aggregate zones or lack comparable observations. |

To import monthly prices, regional yields, and recent production costs, see the [official tables & coverage guide](fuentes-rotacion-peru.md). This inventory provides structured evidence for expanding AgroPhasor; remaining crop cycles, local windows, and recent costs must be verified per cultivar and location before enabling new species in the recommender.
