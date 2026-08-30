# CLAUDE.md — Harvester de precios de botanas (retail MX, zona Querétaro)

Este archivo es el contrato de arquitectura del proyecto. Es NO NEGOCIABLE:
cualquier cambio de diseño que lo contradiga debe discutirse explícitamente
con el usuario antes de implementarse.

## Qué es esto

Un harvester que corre 1 vez al día (GitHub Actions, cron 06:00
America/Mexico_City), extrae el catálogo de botanas saladas y frituras de
supermercados y tiendas de conveniencia con presencia en Querétaro capital
(CP de referencia 76000), y persiste catálogo + histórico de precios en
Postgres (Supabase).

Diseñado para multi-CP a futuro. Corre con un solo CP por ahora.

## Alcance de categoría

Incluye: papas fritas, tortilla chips, churritos/extruidos, cacahuates y
nueces botaneras, semillas, chicharrón, palomitas, multipacks de lo anterior.

Excluye: dulces, chocolates, galletas dulces, barras de cereal.

**Aclaraciones de alcance (decididas en Fase 3, sobre casos que aparecieron
al descubrir la categoría en Chedraui — aplican a todos los retailers, no
solo a este):**
- **Carne seca / jerky/ machaca — EXCLUIDO.** Es una categoría de producto
  distinta (proteína seca, no fritura/extruido), aunque comercialmente se
  venda junto a botanas.
- **Pretzels — EXCLUIDOS, sin excepción** (incluidos los horneados sin
  cobertura dulce).
- **Chía — EXCLUIDA.** Se consume como ingrediente (agua, avena,
  licuados), no a puños como botana lista para comer — a diferencia de
  pepitas/semilla de girasol, que sí cuentan como "semillas".
- **Sí cuentan, para evitar reinterpretarlo cada vez:** palomitas con
  chocolate/caramelo/queso-caramelo (el producto base es palomitas);
  fruta deshidratada con preparación picante mexicana
  (enchilada/con chile/tajín — no la fruta deshidratada simple); trail
  mixes de nueces con fruta deshidratada (salvo que el nombre indique
  explícitamente dulce/chocolatoso); chips/snacks horneados o
  deshidratados de vegetales tipo jícama.
- **NO cuentan:** crema/mantequilla de cacahuate (untable, no se come a
  puños); salsas/dips embotellados aunque el nombre mencione un sabor de
  botana (p.ej. "Salsa Chicharrón..."); fruta deshidratada simple sin
  preparación salada (pasas, ciruela pasa, dátil, arándano natural);
  semillas usadas como ingrediente de cocina (linaza, ajonjolí, comino,
  tapioca, cebada, quinoa, alubia) o de jardín (pasto, para sembrar);
  obleas de amaranto tipo "alegría" (confitería); granola y barras
  tipo cereal/proteína.

## Principio de diseño rector

**Adaptadores por PLATAFORMA (VTEX, Shopify, custom), NUNCA por retailer.**

Agregar un retailer nuevo = agregar un archivo YAML en `retailers/`. Cero
código nuevo. Si agregar un retailer requiere tocar código Python, el diseño
está mal y hay que corregirlo antes de seguir — no hacer la excepción "solo
por esta vez".

Cuando dos retailers comparten plataforma pero difieren en un detalle
(sales channel, formato de cookie de región, endpoint alterno), ese detalle
vive en el YAML como *override*, no como rama de código específica del
retailer.

## Jerarquía de métodos de extracción (de más a menos preferido)

1. **Endpoint JSON documentado o inferido** de la plataforma (VTEX Search
   API, Shopify `/products.json`, etc.). Preferencia absoluta.
2. **Datos embebidos en HTML server-rendered** (`__NEXT_DATA__`,
   `__INITIAL_STATE__`, JSON-LD `Product`/`Offer`) cuando no hay endpoint
   JSON abierto.
3. **Playwright (navegador headless) — ÚLTIMO RECURSO.** Solo si 1 y 2 son
   inviables (SPA sin datos embebidos, o WAF que solo deja pasar tráfico con
   ejecución de JS real). Todo uso de Playwright debe llevar un comentario
   en el código que justifique por qué 1 y 2 fueron descartados para ese
   retailer específico. Ver Fase 7.

Prohibido usar navegador headless si existe un endpoint JSON viable. Esto
se verifica en la Fase 1 (fingerprint) antes de escribir cualquier
adaptador.

## Interfaz única de todo adaptador

Todo adaptador de plataforma (uno por plataforma, no por retailer) expone
exactamente estas cuatro funciones:

```python
def resolve_region(postal_code: str) -> RegionContext: ...
def discover(region_context: RegionContext) -> list[SkuRef]: ...
def fetch(sku_refs: list[SkuRef]) -> RawPayload: ...
def parse(raw: RawPayload) -> list[Product]: ...
```

- `resolve_region`: dado un CP, obtiene el contexto de zona/sucursal/seller
  que hace que los precios devueltos sean los locales y no los nacionales
  por defecto (ver Fase 2 — esto es crítico y se valida empíricamente contra
  el sitio en navegador, no se asume).
- `discover`: dado el contexto de región, produce la lista de SKUs de la
  categoría botanas (ver Fase 3 — tres rutas complementarias: árbol de
  categorías, búsqueda por marca, full-text genérico). Para VTEX esto usa
  la API de catálogo (`/api/catalog_system/pub/products/search`) o
  búsqueda GraphQL — **no da precio confiable**, solo sirve para descubrir
  qué SKUs existen y su metadata (nombre, marca, EAN, categoría).
- `fetch`: dado un lote de SKUs, trae el payload crudo (JSON) del retailer
  **con precio y disponibilidad reales para la región**. Para VTEX esto es
  el endpoint de simulación de checkout
  (`/api/checkout/pub/orderForms/simulation`, batched, con `postalCode` en
  el body) — confirmado en Fase 2 que la API de catálogo devuelve el precio
  nacional genérico del seller `"1"`, no el de la tienda regional; usar esa
  API como fuente de precio contamina todo el histórico. `simulation` es
  stateless (no requiere cookie de sesión, basta el `postalCode` en cada
  request) y acepta batch de varios SKUs por llamada.
- `parse`: combina la metadata de `discover()` con el precio/stock de
  `fetch()` para construir `list[Product]` (modelo pydantic).

El pipeline orquestador (Fase 5/6) llama estas cuatro funciones en orden
para cualquier retailer sin saber qué plataforma es — el YAML del retailer
determina qué implementación de adaptador se usa.

## Reglas de tráfico HTTP

- Rate limit: **1 req/s por dominio**. No por retailer lógico — por dominio,
  porque un mismo dominio puede tener varios sub-servicios.
- Backoff exponencial con jitter, máximo 3 reintentos.
- Timeout: 20s por request.
- User-Agent identificable (no suplantar un navegador real; identifica el
  bot y da un contacto) — **excepto** en la excepción puntual de abajo.
- Respetar `robots.txt`. Si `robots.txt` prohíbe la ruta que necesitamos,
  eso se documenta como hallazgo de Fase 1 (viabilidad ROJA o AMARILLA), no
  se ignora.
- Todo el tráfico es async con `httpx.AsyncClient`.

**Excepción aprobada (Fase 2 y Fase 3, decisión explícita del usuario):**
el bot-shield de VTEX (identificado por el header de respuesta
`x-vtex-janus-router-backend-app`, con `rate-limit-reason: bot` en el
`429`) no es exclusivo del backend de checkout — en Fase 2 se confirmó en
`chk` (`/api/checkout/pub/regions`, `/api/checkout/pub/orderForms/simulation`)
y en Fase 3 se confirmó también en `catalogapi`
(`/api/catalog_system/pub/category/tree/...`, y por extensión el resto de
catálogo/búsqueda). Un cliente con UA identificable y HTTP/1.1 puede ser
bloqueado desde la primera petición, sin haber excedido ningún rate limit
real, y el backoff con reintentos (máx. 3, como manda este mismo documento)
no lo resuelve por sí solo.

Se resuelve sin headless browser, solo igualando la forma de la petición
que hace cualquier visitante anónimo del sitio: `httpx` con `http2=True` y
headers de navegador (`User-Agent` de Chrome, `Origin`, `Referer`,
`sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform`, `sec-fetch-site`,
`sec-fetch-mode`, `sec-fetch-dest`). **La excepción aplica a todo el
tráfico VTEX de un retailer** (checkout y catálogo/búsqueda por igual) —
no solo a las dos llamadas originales de Fase 2. `robots.txt` y cualquier
tráfico fuera de VTEX siguen con el User-Agent identificable del proyecto
salvo que una fase futura encuentre motivo para extenderlo ahí también (y
lo apruebes explícitamente, como aquí). No es evasión de una protección
anti-abuso real — estos endpoints no requieren login ni aceptar términos,
solo responden distinto según la forma de la petición.

## Modelo de datos (resumen — DDL completo en Fase 4)

- `retailers` — un row por retailer, incluye `platform` y `region_context`
  (jsonb) resuelto en Fase 2.
- `products` — catálogo, `UNIQUE(retailer_id, sku)`. `gtin` (EAN/UPC) es la
  llave de cruce entre cadenas — sin GTIN no hay comparación entre
  retailers para ese producto.
- `price_events` — **append-only**. Se inserta un row **solo si** cambia
  `price_list`, `price_sale` o `in_stock` respecto al último evento de ese
  SKU. Nunca se actualiza ni se borra un row existente. Dos corridas el
  mismo día con el mismo precio no deben producir un segundo row.
- `product_matches` — cruce por GTIN entre cadenas.
- `run_log` — una fila por corrida por retailer, con métricas para las
  guardas de calidad (Fase 6).

## Normalización de gramaje y precio — lógica de primera clase

No es limpieza cosmética; es el corazón del valor del proyecto (comparar
$/100g entre marcas y cadenas).

- Extraer gramaje del nombre del producto y de las specs
  (`"Sabritas Adobadas 240g"`, `"12 pzas de 45g"`). Resolver multipacks a
  gramaje total (unidades × gramaje por unidad).
- Calcular `price_per_100g` a partir del gramaje resuelto.
- Si el gramaje no se puede determinar con confianza, marcar el registro
  como `needs_review`. **Nunca inventar o asumir un peso.**
- Precios siempre como `Decimal`. Nunca `float` — errores de redondeo en
  dinero no son aceptables.

## Guardas de calidad (Fase 6) — el requisito más importante del proyecto

El modo de falla real de este sistema no es el crash — es el scraper que
devuelve catálogo vacío o precios en cero silenciosamente durante semanas
mientras todo "corre verde". Las guardas deben **fallar el run ruidosamente**
(`exit != 0` + resumen legible en el step summary de GitHub Actions) cuando:

- `items_ok` < 70% del promedio de los últimos 3 runs exitosos.
- \> 30% de productos con precio nulo o cero.
- \> 40% de SKUs desaparecidos vs. el run anterior.
- Tasa de HTTP 403/429 > 10%.
- \> 20% de registros en `needs_review` por gramaje no resuelto.

No falla el run pero se marca como anomalía para revisión manual:

- Precio de un SKU con variación > 60% en 24h.

## Stack

- Python 3.11+
- `httpx` (async) para todo el tráfico HTTP.
- `pydantic` para modelos (`Product`, `RegionContext`, `SkuRef`, etc.).
- `pytest` para tests. **Los tests no tocan la red** — usan fixtures JSON
  reales guardadas en `/tests/fixtures`, capturadas una vez y versionadas.
- Secretos (connection string de Supabase, etc.) **solo por variables de
  entorno**. Nunca hardcoded, nunca en YAML de retailer.

## Estructura de directorios

```
tools/fingerprint.py       # Fase 1 — detección de plataforma por dominio
core/
  models.py                 # Product, SkuRef, RegionContext, RawPayload (pydantic)
  config.py                 # carga de retailers/<nombre>.yaml -> RetailerConfig
  normalize.py               # gramaje y price_per_100g — Decimal, nunca float
  scope_filter.py            # ¿este producto es "botana"? — lógica de PROYECTO, no de plataforma
  vtex.py                    # adaptador VTEX: resolve_region/discover/fetch/parse
  db.py                       # persistencia Postgres (asyncpg, DATABASE_URL)
  pipeline.py                 # orquestador: despacha por config.platform
retailers/<nombre>.yaml    # config declarativa por retailer
migrations/                 # SQL versionado (aplicado también vía MCP de Supabase cuando está disponible)
tests/fixtures/              # payloads JSON reales para tests offline — nunca tocan la red
scripts/                      # utilidades puntuales (smoke tests, backfill manual) — no es el pipeline de producción
```

## Flujo de trabajo de este proyecto

El proyecto avanza por fases (ver instrucciones originales del usuario).
**Cada fase se detiene al terminar para validación explícita del usuario
antes de avanzar a la siguiente.** No asumir aprobación implícita, no
adelantar trabajo de fases futuras "para ahorrar tiempo".
