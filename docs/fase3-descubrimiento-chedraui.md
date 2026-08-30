# Fase 3 — Descubrimiento de la categoría botanas: Chedraui

Herramientas: [`tools/fase3_discovery_chedraui.py`](../tools/fase3_discovery_chedraui.py)
(las 3 rutas) + [`tools/fase3_classify_chedraui.py`](../tools/fase3_classify_chedraui.py)
(curación fina con reglas explícitas). Exploratorias — no son el adaptador
de producción de Fase 5.

## Conteo de SKUs únicos por ruta (antes de curar)

| Ruta | SKUs únicos encontrados |
|---|---|
| 1. Árbol de categorías (`C:/1/107/10710/` Botanas y frutos secos, `C:/1/111/11104/` Botanas a granel, `C:/1/107/10736/` Granos y semillas filtrado) | 1,396 |
| 2. Búsqueda por marca (28 marcas semilla) | 429 |
| 3. Full-text genérico (7 términos) | 802 |
| **Unión total (antes de curar)** | **1,578** |

602 productos se encontraron **solo** por categoría (ni marca ni texto
libre los habría traído) — confirma que la ruta de categoría es
indispensable, no redundante. Detalle metodológico en la sección final.

## Clasificación final (curación con reglas documentadas)

| Decisión | Cantidad |
|---|---|
| ✅ INCLUDE | **1,370** |
| ❌ EXCLUDE | 152 |
| 🟡 REVISAR (para tu decisión, no autodecidido) | 56 |

## Muestra de 20 productos para tu validación

| Producto | Marca | Precio lista | Ruta(s) | Decisión | Motivo |
|---|---|---|---|---|---|
| Munchies Snack Mix 262.2g | Frito Lay | $165.00 | categoria | ✅ INCLUDE | keyword 'snack' |
| Papas Plaza Del Sol Ajo Vinagre 115g | Plaza del Sol | $69.00 | categoria | ✅ INCLUDE | keyword 'papa' |
| Platanitos Charricos con Chile Jalapeño 50g | Charricos | $22.00 | categoria | ✅ INCLUDE | sin keyword propio, categorizado por Chedraui como Botanas |
| Mix Cosechero Spice 200g | Otras Marcas | $55.00 | categoria | ✅ INCLUDE | sin keyword propio, categorizado por Chedraui como Botanas |
| Palomitas ACT II sabor Caramelo 175g | ACT II | $39.00 | categoria | ✅ INCLUDE | keyword 'palomita' (palomitas dulces/caramelizadas SÍ cuentan, ver criterio) |
| Churros Vitali de Amaranto Chile 500g | Vitali | $197.00 | categoria | ✅ INCLUDE | keyword 'churro' |
| Botana Surtida Sabritas Paketaxo Quexo 208g | Sabritas | $52.00 | las 3 rutas | ✅ INCLUDE | keyword 'botana' |
| Papas Barcel Chip's Sal de Mar 60g | Barcel | $20.00 | las 3 rutas | ✅ INCLUDE | keyword 'papa' |
| Botana Sabritas Sabritones Chile y Limón 160g | Sabritas | $42.00 | las 3 rutas | ✅ INCLUDE | keyword 'botana' |
| Palomitas Act II Queso Explosivo 21g | ACT II | $10.00 | las 3 rutas | ✅ INCLUDE | keyword 'palomita' |
| Chicharrón Prensado Cerdo Atiz kg | Productos Frescos | $122.00 | texto_libre | ✅ INCLUDE | keyword 'chicharrón' (a granel, marca interna no lo descalifica) |
| Bocoles Los Campiranos Chicharrón 600g | Campirano | $86.00 | texto_libre | ✅ INCLUDE | keyword 'chicharrón' |
| Chicharrón Prensado Cerdo por kg | Productos Frescos | $129.00 | texto_libre | ✅ INCLUDE | keyword 'chicharrón' |
| Salsa Chicharrón de Chile Güero El Don 170g | El Don | $123.00 | texto_libre | ❌ EXCLUDE | condimento embotellado (empieza con "Salsa"), no es la botana |
| Barra NotCo Crema Cacahuate 225g | NotCo | $150.00 | texto_libre | ❌ EXCLUDE | crema de cacahuate + formato "barra" — untable/barra proteica, no botana |
| Uva Pasa sin Hueso kg | Frutos Secos | $125.00 | categoria | ❌ EXCLUDE | fruta deshidratada simple, sin preparación salada |
| Semillas Pasto Sol y Sombra Hortaflor | Hortaflor | $113.23 | texto_libre | ❌ EXCLUDE | semilla de **jardín** (para sembrar pasto), no botana |
| Quinoa Naturalika Vita Semilla 100g | Naturalika Vita | $49.90 | texto_libre | ❌ EXCLUDE | semilla usada como ingrediente de cocina, no botana |
| Carne Seca Vik's Jerky con Chile Limón 86g | Vik's Jerky | $157.00 | categoria | 🟡 REVISAR | jerky no está en la lista de subcategorías del brief — ¿lo incluyo? |
| Pretzel Autenta Foods Horneado 150g | Autenta Foods | $26.00 | categoria | 🟡 REVISAR | pretzel no está en la lista del brief; este ejemplo ni siquiera es dulce |
| Chía Orgánica Vivio Foods Semillas 340g | Vivio Foods | $127.00 | categoria, texto_libre | 🟡 REVISAR | "semilla" en sentido literal, pero se usa como ingrediente, no botana |

## Falsos positivos descartados y criterio (152 EXCLUDE)

| # | Motivo | Cantidad | Ejemplo |
|---|---|---|---|
| 1 | Crema/mantequilla de cacahuate (untable) | 36 | Crema de Cacahuate Skippy Cremoso 462g |
| 2 | Condimento/aderezo embotellado (Salsa/Dip) | 27 | Salsa Huichol Botanas 355ml |
| 3 | Fruta deshidratada simple sin preparación salada | 19 | Pasas Sun Maid California |
| 4 | Semilla de jardín/pasto o artículo no alimenticio | 11 | Semillas Pasto Terreno Seco Hortaflor |
| 5 | Oblea (confitería, "alegría" de amaranto) | 11 | Obleas Caxa Amaranto Choco 70g |
| 6 | Semilla/grano como ingrediente de cocina (linaza, ajonjolí, comino, tapioca, cebada, quinoa, alubia) | 10 | Semilla San Elias Linaza 200g |
| 7 | Barra tipo cereal/proteína | 9 | Barras Nature Valley Sweet & Salty |
| 8 | Cubierto de chocolate (y no es palomita) | 5 | Almendras Lotte Chocolate 86g |
| 9 | Dátil (fruta fresca/deshidratada simple) | 4 | Dátil Medjool por Kg |
| 10 | Pan multigrano o miel con semillas | 3 | Pan de Caja...Granos y Semillas |
| 11 | Granola | 3 | (adyacente a barras de cereal) |
| 12 | Marca de granos/legumbres crudos para cocinar (Verde Valle) | 2 | Semillas Verde Valle Maíz Palomero |
| 13 | Fruta deshidratada cubierta de yogurt | 2 | Pasas Sun Maid Vainilla Yogurt |
| 14 | Papa congelada para cocinar (no lista para comer) | 2 | Papas Tradicionales McCain 500g |
| 15 | Platillo preparado/refrigerado (chicharrón guisado) | 2 | Chicharrón El Gallo Giro en Salsa Verde |
| 16 | Palanqueta (turrón de cacahuate) | 1 | Palanqueta Cacahuate Las Sevillanas |
| 17 | Grano de café | 1 | Grano de Café Alif 100g |
| 18 | Dulcería/confitería genérica | 1 | Gomitas Mister Mango Enchilado |
| 19 | Cacao crudo/en polvo | 1 | Cacao Sayab 450g |
| 20 | Trail mix explícitamente dulce/chocolatoso | 1 | Trail First Street Mix Dulces Choco |
| 21 | Galleta (aunque el producto base sea palomitas) | 1 | Palomitas Cookie Pop Oreo Galleta |

**Hallazgo notable:** 34 de estos 152 (categorías 4, 6, 10, 12) vienen del
término genérico "semillas" de la Ruta 3 — el más ruidoso de los 7. Trae
semillas de jardín (Hortaflor), especias/granos de cocina (linaza, comino,
tapioca, cebada, quinoa), pan multigrano y hasta alimento para aves
silvestres, solo porque contienen la palabra "semilla(s)". Sin curación
manual, un tercio de los "falsos positivos por semilla" habría contaminado
la categoría con productos que no son botanas de ningún tipo. Esto confirma
por qué el brief pidió reportar los falsos positivos antes de avanzar.

## Decisiones de criterio que SÍ tomé (para que las audites)

- **Palomitas con chocolate/caramelo/queso-caramelo SÍ se incluyen** — el
  producto base es palomitas (explícitamente en tu lista), el sabor no lo
  saca de la categoría. Solo se excluye si trae **galleta** mezclada
  (ej. "Cookie Pop Oreo").
- **Fruta deshidratada con preparación picante mexicana (enchilada/con
  chile/tajín) SÍ se incluye** — es una botana salada-picante real
  (mango/arándano/kiwi/higo enchilado), distinta de la fruta deshidratada
  simple (pasas, ciruela pasa, arándano natural) que se excluye.
- **Trail mixes de nueces con fruta deshidratada SÍ se incluyen**, salvo
  que el nombre indique explícitamente "dulce"/"chocolatoso".
- **Jícama horneada/deshidratada (chips de jícama) SÍ se incluye** —
  inicialmente la excluí asumiendo que era producto fresco de verdulería;
  al revisar la muestra vi que son chips horneados empacados (Half & Half,
  Vitali, Beatrichef), corregí el criterio.
- **"Donitas" (Totis, Chechitos) SÍ se incluyen** — mismo error inicial:
  asumí que era pan dulce; son un snack frito en forma de anillo con
  sabores salados (chile y limón, sal y limón), no repostería.
- **Chicharrón/nueces/semillas vendidos a granel bajo la marca interna de
  Chedraui "Productos Frescos"/"Frutas y Verduras" SÍ se incluyen** —
  probé excluirlos en bloque asumiendo que esa marca = perecedero, pero
  también cubre chicharrón y frutos secos a granel legítimos. Se revirtió.

## Judgment calls que te dejo a ti (56 REVISAR)

| Categoría | Cantidad | Por qué no lo decidí solo |
|---|---|---|
| Carne seca / jerky (Jack Link's, Vik's Jerky, Steakos, machaca) | 31 | No está en tu lista de subcategorías (papas, tortilla chips, churritos, cacahuates/nueces, semillas, chicharrón, palomitas). Comercialmente sí se vende junto a botanas. |
| Pretzels | 19 | Tampoco está en tu lista. Los que encontré vienen cubiertos de chocolate/canela dulce (yo los habría excluido por eso de todos modos), pero apareció al menos un pretzel horneado simple sin cobertura dulce — ahí sí es un caso limpio de "¿cuenta o no?". |
| Chía | 6 | Es "semilla" en sentido literal de tu lista, pero se consume como ingrediente (agua, avena, licuados), no a puños como botana. |

## Metodología (para que audites el proceso, no solo el resultado)

- **Ruta 1 — categorías:** el filtro correcto de VTEX es la ruta completa
  desde el departamento raíz (`fq=C:/1/107/10710/`), no el id de hoja
  solo — lo until verifiqué contra `categoriesIds` de un producto conocido
  antes de asumir la sintaxis. Las 3 categorías consultadas:
  - `/1/107/10710/` Botanas y frutos secos (despensa) — 1,370 productos
  - `/1/111/11104/` Botanas (a granel) — 9 productos
  - `/1/107/10736/` Granos y semillas — 250 productos, de los cuales solo
    17 pasaron un filtro de keyword (el resto son granos/legumbres de
    cocina, no botanas — coherente con lo que encontró la Ruta 3).
- **Ruta 2 — marca:** de las 28 marcas semilla, 3 no dieron resultados con
  ese nombre exacto en Chedraui (Golden Nuts, Hot Nuts, Big Mix SÍ dieron
  resultado tras corregir un bug de encoding — ver abajo); Vualá dio 3
  resultados pero ninguno pasó el filtro (posible ausencia de esa marca en
  el catálogo o nombre distinto).
- **Ruta 3 — texto libre:** el término "semillas" resultó ser, por lejos,
  el más ruidoso de los 7 (ver sección de falsos positivos).
- **Bug de encoding corregido en el camino:** `httpx` codifica espacios
  como `+` en query params por default; el borde de Chedraui/VTEX rechaza
  `+` con `400 "Bad Request! Scripts are not allowed!"` (una regla WAF
  ingenua) pero acepta `%20` sin problema. Sin corregirlo, toda búsqueda
  de dos palabras («papas fritas», «Golden Nuts», «Act II»...) fallaba
  silenciosamente — lo detecté porque esos términos daban 0 resultados en
  vez de error, y confirmé la causa real antes de seguir.

## Decisión final del usuario sobre los 3 rubros de REVISAR

| Categoría | Cantidad | Decisión |
|---|---|---|
| Carne seca / jerky | 31 | **Excluir** — categoría de producto distinta (proteína seca, no fritura/extruido) |
| Pretzels | 19 | **Excluir todos**, sin excepción (incluso los horneados sin cobertura dulce) |
| Chía | 6 | **Excluir** — se consume como ingrediente, no como botana lista para comer |

Estas tres decisiones ya quedaron codificadas en
`tools/fase3_classify_chedraui.py` y documentadas en `CLAUDE.md` como
aclaraciones de alcance que aplican a **todos los retailers**, no solo a
Chedraui — para no tener que re-litigarlas cuando aparezcan en el catálogo
de otra cadena.

## Números finales (con las 3 decisiones aplicadas)

| Decisión | Cantidad |
|---|---|
| ✅ INCLUDE | **1,370** |
| ❌ EXCLUDE | 208 |
| 🟡 REVISAR | 0 |

**Fase 3 queda cerrada para Chedraui.** Categoría delimitada: 1,370 SKUs
únicos de botanas saladas y frituras, con criterio de inclusión/exclusión
completamente documentado y auditable.

## Siguiente paso

Pasar a Fase 4 (modelo de datos / DDL) — a la espera de tu visto bueno
para avanzar.
