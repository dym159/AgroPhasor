# Inventario de 60 cultivos para rotaciones en Perú

Este inventario cubre 60 grupos de cultivo y conserva 71 registros de productos o fichas. Los productos de maíz, caña, cebada, arveja, haba y los ajíes y pimientos se mantienen visibles dentro de su grupo para comparar sus datos sin contar cada salida comercial como un cultivo distinto. El rocoto se conserva como grupo propio. La selección prioriza especies transitorias, raíces, hortalizas y forrajes. El ámbito de aplicación abarca los 24 departamentos y el Callao. Las fuentes tienen distintos niveles de cobertura.

## Prioridad para AgroPhasor

El criterio de inclusión es el cultivo documentado en el Perú. Las cifras se refieren a producción, parcelas o ensayos peruanos. El orden de trabajo de AgroPhasor toma en cuenta la prioridad oficial, la utilidad para rotar familias y la cobertura de Costa, Sierra y Selva.

| Prioridad | Cultivos y productos | Criterio |
| --- | --- | --- |
| Primera incorporación | Papa, arroz, maíz amarillo duro, maíz amiláceo, maíz choclo, quinua, yuca y frijol grano seco. | Los siete primeros son el foco del Marco Orientador de Cultivos 2025/2026, que les atribuye en conjunto el 33 % del valor bruto de la actividad agrícola nacional. El frijol aporta una leguminosa al catálogo y figura entre los cultivos destacados por las intenciones de siembra 2026/2027. [Marco Orientador de MIDAGRI](https://www.gob.pe/institucion/midagri/noticias/1231067-midagri-area-sembrada-2025-2026-crecera-5-4-en-comparacion-a-ultimas-cinco-campanas-agricolas) · [Resultados ENIS](https://www.gob.pe/institucion/midagri/noticias/1418927-midagri-proyecta-mas-de-2-millones-de-hectareas-de-siembra-impulsadas-por-maiz-papa-y-frijol) |
| Ampliación de los transitorios priorizados | Ajo, ají, algodón, arveja seca y verde, camote, cebada, cebolla, olluco, páprika, rocoto, tomate, trigo, zanahoria y zapallo. | Completan los 23 productos de la ENIS 2026/2027, todos presentes en el inventario. MIDAGRI los seleccionó por su aporte productivo, superficie y relevancia para la seguridad alimentaria. [Lista oficial ENIS](https://www.gob.pe/institucion/midagri/noticias/1386511-midagri-inicia-la-encuesta-nacional-de-intenciones-de-siembra-para-la-campana-agricola-2026-2027) |
| Complementos de rotación por zona | Entre otros, haba, tarwi y vicia en zonas andinas y caupí en la Costa norte, según las fichas varietales. | Aportan opciones para alternar familias en parcelas con condiciones adecuadas. Sus ventanas y ciclos se verifican por cultivar y zona. |
| Cultivos de importancia económica con ocupación prolongada | Entre otros, café, cacao, palta, uva, aceituna, arándano, plátano y palma aceitera. | Su producción figura en informes nacionales. Para recomendarlos se necesita representar establecimiento, años de ocupación o cosechas sucesivas. [Balance agrícola nacional 2025](https://www.gob.pe/institucion/midagri/noticias/1347928-midagri-sector-agropecuario-alcanzo-un-crecimiento-de-4-8-al-cierre-del-ano-2025) · [Producción agrícola 2026](https://www.gob.pe/institucion/midagri/noticias/1428237-midagri-sector-agropecuario-experimento-crecimiento-de-1-2-en-primer-semestre-del-ano) |

Las prioridades anteriores orientan la incorporación al producto. El inventario de 60 grupos incluye cultivos complementarios y sistemas de ciclo largo, además de los transitorios de la ENIS. Para medir importancia económica reciente se puede usar el [valor bruto de producción por producto de MIDAGRI](https://www.gob.pe/institucion/midagri/informes-publicaciones/7800032-informe-mensual-del-valor-bruto-de-la-produccion-agropecuaria-2026).

## Costos, rendimientos y precios disponibles

- **Costo y rendimiento ENA** corresponden a estimaciones históricas nacionales de **2018**. Los costos se expresan en soles nominales por hectárea cosechada. El rendimiento se transcribe cuando el capítulo identifica explícitamente un promedio en kg/ha.
- **Precio en chacra del proyecto** muestra el mínimo y el máximo entre las zonas del [CSV existente](../backend/data/precios_chacra_midagri_2025_2026.csv). El archivo carece de fecha por fila. Estos rangos describen el archivo y no se combinan con los costos de 2018 para inferir margen actual.
- **—** indica que este inventario carece de un valor verificado y comparable. Se conservan por separado las presentaciones comerciales cuando el costo, rendimiento o precio corresponden a productos distintos.
- La clasificación indica cómo tratar cada grupo en la planificación. Los grupos de ciclo largo, las plantaciones perennes y los forrajes de varios cortes necesitan reglas de ocupación de parcela propias. Los transitorios también requieren comprobar ventana local, cultivar y régimen de agua antes de sugerirlos.

La clasificación contiene **32 transitorios**, **5 forrajes de varios cortes o permanencia variable** y **23 cultivos perennes, de ciclo largo o de cosechas sucesivas**.

Hay **63 registros con costo histórico**, **61 con rendimiento histórico extraído** y **47 con precio de referencia en el archivo del proyecto**.

### Transitorio

| Cultivo | Producto | Costo ENA (S/ por ha) | Rendimiento ENA (kg/ha) | Precio del CSV (S/ por kg) | Fuente |
| --- | --- | ---: | ---: | ---: | --- |
| Ajíes y pimientos | Páprika | 15 096,9 | 7 877 | 1,80–12,00 (9 zonas) | [ENA, p. 107](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=107) |
| Ajíes y pimientos | Ají | 15 985,3 | 21 511 | 0,36–12,00 (19 zonas) | [ENA, p. 141](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=141) |
| Ajíes y pimientos | Pimiento | 32 838,6 | 34 334 | 1,30–3,20 (8 zonas) | [ENA, p. 155](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=155) |
| Ajíes y pimientos | Piquillo | 30 281,0 | 25 112 | 0,30–2,00 (3 zonas) | [ENA, p. 163](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=163) |
| Ajo | Ajo | 9 952,2 | 7 684 | 1,60–10,68 (18 zonas) | [ENA, p. 123](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=123) |
| Algodón | Algodón | 5 003,9 | 2 702 | 1,50–7,00 (8 zonas) | [ENA, p. 119](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=119) |
| Arroz | Arroz | 4 723,98 | 8 471 | 0,70–3,38 (16 zonas) | [ENA, p. 53](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=53) |
| Arveja | Arveja grano verde | 2 783,4 | 2 371 | 1,93–4,78 (19 zonas) | [ENA, p. 113](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=113) |
| Arveja | Arveja grano seco | 641,6 | 565 | 2,19–5,84 (17 zonas) | [ENA, p. 137](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=137) |
| Avena Forrajera | Avena Forrajera | 1 504,4 | 15 181 | 0,18–0,97 (13 zonas) | [ENA, p. 89](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=89) |
| Brócoli | Brócoli | 4 901,5 | 11 084 | — | [ENA, p. 171](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=171) |
| Camote | Camote | 3 011,0 | 14 752 | 0,80–2,50 (20 zonas) | [ENA, p. 115](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=115) |
| Cañihua | Cañihua | — | — | — | [INIA, p. 398](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Caupí | Caupí | — | — | — | [INIA, p. 208](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Cebada | Cebada | 1 548,2 | 1 508 | 1,00–3,21 (20 zonas) | [ENA, p. 111](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=111) |
| Cebada | Cebada forrajera | 7 692,9 | 13 766 | 0,30–1,00 (8 zonas) | [ENA, p. 151](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=151) |
| Cebolla | Cebolla | 14 925,2 | 54 836 | 0,76–2,00 (19 zonas) | [ENA, p. 85](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=85) |
| Frijol grano seco | Frijol grano seco | 1 281,6 | 1 363 | 1,98–9,02 (23 zonas) | [ENA, p. 101](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=101) |
| Haba | Haba grano seco | 1 261,0 | 1 110 | 1,25–6,00 (18 zonas) | [ENA, p. 129](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=129) |
| Haba | Haba grano verde | 3 674,2 | 4 288 | — | [ENA, p. 167](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=167) |
| Kiwicha | Kiwicha | — | — | — | [INIA, p. 390](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Lechuga | Lechuga | 16 568,5 | 11 327 | — | [ENA, p. 181](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=181) |
| Lenteja | Lenteja | — | — | — | [INIA, p. 248](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Maíz | Maíz amarillo duro | 3 067,2 | 4 657 | 0,82–2,87 (24 zonas) | [ENA, p. 63](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=63) |
| Maíz | Maíz amiláceo | 1 421,2 | 1 302 | 2,08–5,89 (20 zonas) | [ENA, p. 83](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=83) |
| Maíz | Maíz choclo | 2 772,5 | 9 776 | 0,47–4,19 (21 zonas) | [ENA, p. 91](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=91) |
| Maíz | Maíz chala | 4 673,5 | 46 769 | 0,26–3,00 (10 zonas) | [ENA, p. 105](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=105) |
| Oca | Oca | 5 520,0 | 5 520 | 0,83–3,85 (17 zonas) | [ENA, p. 161](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=161) |
| Olluco | Olluco | 4 407,2 | 5 215 | 0,67–3,93 (18 zonas) | [ENA, p. 127](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=127) |
| Pallar | Pallar grano seco | 3 633,3 | 1 845 | 1,04–6,00 (7 zonas) | [ENA, p. 189](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=189) |
| Papa | Papa | 10 405,50 | 21 795 | 0,52–12,22 (20 zonas) | [ENA, p. 55](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=55) |
| Quinua | Quinua | 5 906,2 | 2 630 | 3,00–6,19 (16 zonas) | [ENA, p. 125](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=125) |
| Sandía | Sandía | 7 744,8 | 25 978 | — | [ENA, p. 173](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=173) |
| Tarwi | Tarwi | — | — | — | [INIA, p. 242](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Tomate | Tomate | 20 077,8 | 123 833 | 0,37–4,00 (22 zonas) | [ENA, p. 103](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=103) |
| Trigo | Trigo | 1 290,9 | 1 346 | 0,90–5,50 (20 zonas) | [ENA, p. 109](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=109) |
| Triticale | Triticale | — | — | — | [INIA, p. 320](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Vicia | Vicia | — | — | — | [INIA, p. 352](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Yuca | Yuca | 3 713,2 | 12 525 | 0,42–2,94 (23 zonas) | [ENA, p. 77](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=77) |
| Zanahoria | Zanahoria | 6 830,8 | 26 153 | 0,54–2,50 (19 zonas) | [ENA, p. 147](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=147) |
| Zapallo | Zapallo | 5 085,0 | 20 608 | 0,49–2,39 (25 zonas) | [ENA, p. 135](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=135) |

### Forraje de varios cortes o permanencia variable

| Cultivo | Producto | Costo ENA (S/ por ha) | Rendimiento ENA (kg/ha) | Precio del CSV (S/ por kg) | Fuente |
| --- | --- | ---: | ---: | ---: | --- |
| Alfalfa | Alfalfa | 3 608,7 | 49 236 | 0,16–1,00 (20 zonas) | [ENA, p. 65](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=65) |
| Braquearia | Braquearia | 388,5 | 45 537 | — | [ENA, p. 81](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=81) |
| Pasto de elefante | Pasto de elefante | 512,9 | 19 583 | — | [ENA, p. 117](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=117) |
| Rye grass | Rye grass | 9 624,9 | 73 377 | — | [ENA, p. 149](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=149) |
| Trébol | Trébol | 1 336,9 | 34 273 | — | [ENA, p. 179](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=179) |

### Perenne, ciclo largo o cosechas sucesivas

| Cultivo | Producto | Costo ENA (S/ por ha) | Rendimiento ENA (kg/ha) | Precio del CSV (S/ por kg) | Fuente |
| --- | --- | ---: | ---: | ---: | --- |
| Aceituna | Aceituna | 6 925,1 | 4 535 | 2,38–8,19 (8 zonas) | [ENA, p. 79](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=79) |
| Alcachofa | Alcachofa | 12 835,4 | 16 381 | 1,60–4,20 (7 zonas) | [ENA, p. 93](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=93) |
| Arándano | Arándano | 40 754,53 | 6 504 | 7,00–15,00 (8 zonas) | [ENA, p. 67](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=67) |
| Cacao | Cacao | 5 671,2 | 1 489 | 6,94–24,11 (16 zonas) | [ENA, p. 71](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=71) |
| Café | Café | 2 130,1 | — | — | [ENA, p. 57](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=57) |
| Camu camu | Camu camu | — | — | — | [INIA, p. 436](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) |
| Caña de azúcar | Caña para azúcar | 6 396,4 | 123 796 | — | [ENA, p. 73](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=73) |
| Caña de azúcar | Caña de azúcar para alcohol | 4 457,3 | 72 303 | — | [ENA, p. 153](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=153) |
| Caña de azúcar | Caña de azúcar para etanol | 6 067,6 | 123 785 | — | [ENA, p. 159](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=159) |
| Espárrago | Espárrago | 11 017,5 | — | 2,00–7,75 (5 zonas) | [ENA, p. 59](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=59) |
| Fresa | Fresa | 7 954,1 | 13 283 | — | [ENA, p. 191](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=191) |
| Granada | Granada | 15 827,1 | 16 193 | — | [ENA, p. 175](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=175) |
| Limón | Limón | 7 412,9 | 19 245 | 0,60–4,64 (24 zonas) | [ENA, p. 121](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=121) |
| Mandarina | Mandarina | 10 452,6 | 39 349 | 0,50–3,13 (18 zonas) | [ENA, p. 87](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=87) |
| Mango | Mango | 8 244,1 | 19 478 | 0,36–5,24 (23 zonas) | [ENA, p. 97](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=97) |
| Maracuyá | Maracuyá | 18 761,6 | 11 153 | — | [ENA, p. 177](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=177) |
| Naranja | Naranja | 5 778,6 | 24 482 | 0,40–2,50 (25 zonas) | [ENA, p. 95](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=95) |
| Orégano | Orégano | 3 212,3 | 2 332 | 1,00–12,00 (9 zonas) | [ENA, p. 133](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=133) |
| Palma aceitera | Palma aceitera | 4 238,5 | 17 698 | 0,46–0,71 (4 zonas) | [ENA, p. 194](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=194) |
| Palta | Palta | 13 373,3 | 13 490 | 0,51–17,18 (24 zonas) | [ENA, p. 75](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=75) |
| Papaya | Papaya | 3 940,3 | 11 668 | 0,43–3,80 (23 zonas) | [ENA, p. 157](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=157) |
| Piña | Piña | 5 068,0 | 17 180 | 0,42–2,20 (13 zonas) | [ENA, p. 99](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=99) |
| Plátano | Plátano | 13 352,2 | 21 760 | 0,44–3,60 (25 zonas) | [ENA, p. 69](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=69) |
| Rocoto | Rocoto | 2 102,5 | 8 513 | — | [ENA, p. 165](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=165) |
| Uva | Uva | 52 802,2 | 19 915 | 2,00–5,99 (14 zonas) | [ENA, p. 61](https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/costos-de-produccion-v7.pdf#page=61) |

## Ciclos y ventanas con respaldo técnico

Las fechas corresponden a los cultivares y zonas indicados. Los números de página de INIA son los impresos en el compendio. «Pot.» denota rendimiento potencial de la ficha.

| Cultivo y referencia | Zona documentada | Ciclo y momento de medición | Siembra → cosecha | Rendimiento de la ficha |
| --- | --- | --- | --- | --- |
| Papa Canchán, INIA p. 58 | Junín, Huancavelica, Huánuco, Áncash y Lima | 120 días | Octubre–diciembre → enero–abril | — |
| Maíz amiláceo Cumbemaino, INIA p. 116 | Cajamarca y La Libertad | 165–180 días | Noviembre–diciembre → abril–junio | Pot. 4 t/ha |
| Maíz amiláceo Blanco Quispicanchi | Cusco | 240–255 días a madurez | — | [Ficha de INIA 618](https://www.inia.gob.pe/wp-content/uploads/investigacion/programa/sistProductivo/variedad/maiz/INIA_618.pdf) |
| Frijol Costacen, INIA p. 182 | Piura, Lambayeque, La Libertad, Arequipa, Moquegua y Lima | 90–125 días | Mayo–junio → septiembre–octubre | 3,1 t/ha promedio |
| Frijol Canario Camanejo, INIA p. 184 | Arequipa y Áncash | 150 días | Marzo–junio → octubre–noviembre | 2–2,5 t/ha promedio |
| Frijol Perla Cusco, INIA p. 186 | Ayacucho, Cusco y Apurímac | 121–128 días | Septiembre–enero → enero–mayo | 1,5–1,8 t/ha promedio |
| Frijol Martín Cusco, INIA p. 188 | Ayacucho, Cusco y Apurímac | 120 días | Septiembre–enero → enero–mayo | 1,5–2 t/ha promedio |
| Caupí Vaina Verde, INIA p. 208 | Lambayeque, Piura, Tumbes y La Libertad | 80–100 días | Octubre–marzo → enero–junio | Pot. 3 t/ha |
| Haba Siwina, INIA p. 216 | Apurímac, Puno, Cusco y Ayacucho | 158 días | Septiembre–octubre → febrero–marzo | 2,5–3 t/ha promedio |
| Arveja Remate, INIA p. 236 | Junín, Cajamarca, Huancavelica, Áncash y Ayacucho | 150 días | Septiembre–diciembre → enero–abril | — |
| Tarwi Masacanchino, INIA p. 242 | Apurímac, La Libertad, Cajamarca y Amazonas | 208 días | Octubre–noviembre → mayo–junio | Pot. 1,4–1,66 t/ha |
| Lenteja Argentino Precoz, INIA p. 248 | Cajamarca, Piura, Lambayeque y La Libertad | 120–130 días | Sierra enero–febrero, Costa abril–julio. Verificar cosecha por zona | 0,8–1 t/ha promedio |
| Arroz La Unión 23, INIA p. 254 | Cajamarca y Amazonas | 125–140 días | La ficha indica todo el año para siembra y cosecha. Aplicar disponibilidad de agua y campaña | Pot. 10 t/ha |
| Trigo Antapampino, INIA p. 288 | Sierra, entre otros Cajamarca, Pasco, Junín, Huancavelica y Huánuco | 125 días | Noviembre–diciembre → marzo–abril | Pot. 4,8–5 t/ha |
| Triticale Salkantay, INIA p. 320 | Sierra, entre otros Pasco, Junín, Huancavelica, Huánuco y Ayacucho | 103 días | Marzo–diciembre → julio–abril | Pot. 4,66 t/ha de grano |
| Cebada La Milagrosa, INIA p. 326 | Sierra, entre otros Cajamarca, Pasco, Junín, Huancavelica y Huánuco | 137 días | Noviembre–enero → abril–junio | Pot. 4,5 t/ha |
| Avena Katekyl, INIA p. 334 | Cajamarca, Amazonas y La Libertad | Forraje 90–100 días; semilla 180–200 días | Octubre–diciembre → forraje enero–marzo o grano abril–junio | — |
| Vicia Caxamarca, INIA p. 352 | Sierra, entre otros Cajamarca, Cusco, Junín, Ayacucho y Pasco | Forraje 95 días; grano 195 días | Para forraje noviembre–febrero → febrero–mayo; grano mayo–julio, según ficha | — |
| Rye grass Kumymarca, INIA p. 358 | Cajamarca | Semiperenne, 30–45 días para pastoreo o corte según ficha | Septiembre–octubre → noviembre–diciembre | — |
| Quinua Atipaq, INIA p. 364 | Puno | 150–160 días | Octubre–noviembre → marzo–abril | Pot. 3,5–6 t/ha |
| Kiwicha La Frondosa, INIA p. 390 | Puno, Cusco, Ayacucho, Apurímac y Huancavelica | 150–155 días | Noviembre–diciembre → abril–junio | 2,5 t/ha promedio |
| Cañihua Illpa, INIA p. 398 | Puno | 140 días | Octubre–noviembre → febrero–abril | 2,5–3 t/ha promedio |
| Algodón Colorina, INIA p. 400 | San Martín | 168 días | Diciembre–enero → mayo–junio; febrero–marzo → julio–agosto | — |
| Caña PVF 03-115, INIA p. 416 | Lambayeque, Piura y Cajamarca | 18 meses | La ficha registra enero y julio para siembra y julio y noviembre para cosecha | — |
| Ajo Donajus, INIA p. 422 | Arequipa, Ica, Lima, Huaraz y Chimbote | 5 meses | Abril–julio → septiembre–diciembre | Pot. 17 t/ha |
| Zanahoria Huaralina Precoz, INIA p. 430 | Lima, Ica y Junín | Costa 90–110 días; Sierra 110–120 días | Costa abril–octubre → agosto–febrero; en Sierra, la ficha indica siembra todo el año | — |
| Camote Bondadosa, INIA p. 92 | La Libertad, Piura, Lima, Ica y Lambayeque | 3,5–4 meses | La ficha indica todo el año | Pot. 60 t/ha |
| Oca K’eny Rojo, INIA p. 106 | Puno | 190 días | Septiembre → abril | 24,5 t/ha promedio |
| Pallar Iqueño Precoz, INIA p. 442 | Ica | 125 días | Marzo–abril → julio–septiembre | Pot. 0,95 t/ha |
| Camu camu Vitahuayo, INIA p. 436 | Loreto, San Martín y Ucayali | Requiere dato de establecimiento y horizonte perenne | La ficha indica siembra todo el año y cosecha noviembre–abril | — |
| Yuca, observatorio regional | Amazonas, Junín, Ucayali y San Martín | Rezagos estimados de 8, 12, 9 y 6 meses, respectivamente | Siembras más concentradas en agosto–diciembre en Amazonas y Junín, agosto–octubre en Ucayali y enero–abril en San Martín | [Observatorio MIDAGRI, cuadros 5–8](https://cdn.www.gob.pe/uploads/document/file/6064998/4344772-observatorio-de-siembras-y-perspectivas-de-produccion-yuca.pdf?v=1712843397) |
| Olluco, guía de campo | Andes, según altitud y variedad | 180–220 días a cosecha | — | [Guía de cultivos andinos](https://www2.congreso.gob.pe/sicr/cendocbib/con4_uibd.nsf/EA54F80C677EA73C05257D20007700FD/%24FILE/Gu%C3%ADaCampoCultivosAndinos.pdf) |
| Ají páprika, manual del INIA | Contexto del manual de páprika | 120–150 días a madurez de cosecha | — | [Manual INIA, p. 18](https://repositorio.inia.gob.pe/server/api/core/bitstreams/4023af50-e2e0-45fd-b047-8e3cd142ae66/content) |

[Compendio de cultivares del INIA](https://repositorio.inia.gob.pe/server/api/core/bitstreams/00d5f440-ebef-4b68-a70a-d240ac46bc1f/content) · [Calendario Costa](https://repositorio.inia.gob.pe/items/c5a4c11c-d0c7-41b9-b0bf-fe200c2bf403) · [Calendario Sierra](https://repositorio.inia.gob.pe/items/545185cc-25ea-42d7-b877-60d6e3e24978/full) · [Calendario Selva](https://repositorio.inia.gob.pe/items/682cd18e-1b10-40b7-b6cc-6a5bc43c25f0)

## Verificaciones pendientes para activar un cultivo

| Decisión del recomendador | Evidencia requerida |
| --- | --- |
| Encadenar siembra y cosecha | Registrar familia botánica, cultivar, evento que mide el ciclo, meses aptos, zona y riego. Ajustar el horizonte en los cultivos de varios cortes y las plantaciones permanentes. |
| Comparar rendimiento | Usar observaciones del producto comercial y el ámbito adecuado. Los potenciales varietales sirven para contrastar el simulador y deben conservar su etiqueta. |
| Calcular margen | Emparejar precio del mismo producto y mes con costos recientes por zona, en la misma moneda. Cotejar los valores extremos del CSV con el cuadro de origen y su unidad antes de usarlos. |
| Cubrir una zona sin dato | Confirmar si el departamento o el Callao cuenta con una observación independiente. Pedir al usuario el dato local cuando la fuente disponible agrupe zonas o carezca de una observación comparable. |

Para importar precios por mes, rendimientos regionales y costos recientes, véase la [guía de cuadros oficiales y cobertura](fuentes-rotacion-peru.md). Este inventario es evidencia para ampliar AgroPhasor. Los ciclos, las ventanas y los costos recientes pendientes deben verificarse por cultivar y lugar antes de habilitar un nuevo cultivo en el recomendador.
