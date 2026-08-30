# Fase 5 — Adaptador VTEX + pipeline

## Qué se construyó

- [core/models.py](../core/models.py) — `RegionContext`, `SkuRef`, `RawPayload`, `Product` (pydantic).
- [core/config.py](../core/config.py) + [retailers/chedraui.yaml](../retailers/chedraui.yaml) — config declarativa (Fase 2/3 ya resueltas, volcadas aquí).
- [core/normalize.py](../core/normalize.py) — gramaje y `price_per_100g`, con `Decimal` en todo, nunca inventa un peso.
- [core/scope_filter.py](../core/scope_filter.py) — la curación de Fase 3, generalizada como código de producción (lógica de proyecto, no de VTEX — un adaptador Shopify futuro la reusaría igual).
- [core/vtex.py](../core/vtex.py) — `resolve_region` / `discover` / `fetch` / `parse`.
- [core/db.py](../core/db.py) — persistencia (upsert products, diff append-only, run_log).
- [core/pipeline.py](../core/pipeline.py) — orquestador.
- `tests/` — 40 tests, todos verdes, ninguno toca la red (fixtures reales en `tests/fixtures/`).

## Un ajuste a la interfaz de CLAUDE.md que hice y por qué

El esbozo original de Fase 0 tenía `discover(region_context) -> list[SkuRef]`, etc. En la práctica cada función necesita también el `RetailerConfig` (dominio, CP, categorías, marcas — varían por retailer aunque la plataforma sea la misma VTEX) y un `httpx.AsyncClient` compartido (para reusar conexión HTTP/2). Firma real:

```python
resolve_region(client, config)              -> RegionContext
discover(client, config, region)              -> list[SkuRef]
fetch(client, config, region, sku_refs)        -> RawPayload
parse(raw, config)                              -> list[Product]   # única sin I/O
```

`parse()` sigue siendo la única función sin I/O — es la que se prueba con fixtures reales, tal como pedía el brief.

## Dos hallazgos nuevos en el camino (no eran obvios desde Fase 2/3)

1. **`Contenido del empaque` es una spec estructurada de VTEX**, no algo que haya que inventar parseando el nombre: `"1 pieza de 160g"`, `"1 pz de 200g"` — casi idéntica al ejemplo del brief (`"12 pzas de 45g"`). Es la fuente de gramaje más confiable, antes que el nombre. La regex de multipack se probó con el ejemplo sintético del brief porque **no encontré ningún producto real en Chedraui con ese patrón exacto en el nombre** — sí lo hay en la spec, con conteo 1.
2. **El campo `promo_label` no es texto legible** — cuando hay promo activa, VTEX devuelve un identificador interno (`"discount@shipping-c3a51ff1-...#5419b747-..."`), no `"20% de descuento"`. Se captura igual (sirve para detectar que HAY una promo), pero no es humano-legible todavía — lo dejo anotado como limitación conocida, no lo resolví con datos ficticios.

## Validación de extremo a extremo (con datos reales, dos corridas)

Corrí el pipeline completo dos veces contra Chedraui real (categoría "Botanas a granel", 9 productos — la más chica de Fase 3, para una prueba completa y rápida) e inserté los resultados en el Supabase real vía SQL:

| Corrida | descubiertos | en alcance | price_events nuevos |
|---|---|---|---|
| 1 | 9 | 9 (0 excluidos) | 9 |
| 2 (minutos después, red real de nuevo) | 9 | 9 | **0** |

La segunda corrida confirmó que los 9 productos tenían el mismo precio y stock que la primera — el diff append-only correctamente **no insertó ningún price_event nuevo**. Estado final en la base: 1 retailer, 9 products, **9** price_events (no 18), 2 run_log. Idempotencia probada con corridas reales, no simulada.

Un ejemplo concreto de lo que quedó guardado — SKU 3897073, "Chicharrón Susalia Cerdo 75g": `price_sale=$41.50`, `net_weight_g=75` (de la spec), `price_per_100g=$55.3333`, `seller=chedrauimx0268` (la tienda real de Querétaro, no el seller genérico), `in_stock=false`.

## Actualización: `core/db.py` ya corrió con `asyncpg` real (2026-08-30)

La brecha de arriba se cerró. El usuario pasó el `DATABASE_URL` real
(Transaction pooler de Supabase) y corrí `python run.py --retailer
chedraui` de punta a punta, sin pasar por el MCP para nada de la
persistencia. Resultado real, catálogo completo:

```
descubiertos=2084 en_alcance=1642 items_ok=1642 items_err=0
price_events_nuevos=1533 needs_review=32 (1.9%) precio_nulo=48 (2.9%)
tasa_403_429=0.5%
guardas: TODAS pasaron (items_ok_vs_promedio, precio_nulo,
skus_desaparecidos, tasa_403_429, needs_review) + 0 anomalías de precio 24h
```

De los 1642 price_events totales, 1533 son nuevos y 109 no generaron
evento porque ya existían con el mismo precio/stock de una carga manual
anterior — el diff append-only se comportó exactamente como debía incluso
en un escenario mixto (productos ya conocidos + productos nuevos), no
solo en el caso limpio de "todo nuevo" o "todo repetido" de las pruebas
anteriores.

**Bug real encontrado y corregido en el camino:** la primera corrida
falló con `DuplicatePreparedStatementError`. Causa: el connection string
que Supabase recomienda por default (Transaction pooler, puerto 6543) usa
PgBouncer en `pool_mode=transaction`, que no soporta prepared statements
— y `asyncpg.create_pool()` los usa por default. Se resuelve pasando
`statement_cache_size=0` al crear el pool (ver `core/db.py`). Esto no se
podía haber encontrado sin correr contra el Postgres real — es exactamente
el tipo de bug que la limitación de abajo (ya resuelta) estaba escondiendo.

## Qué NO se hizo (correctamente, es Fase 6/7)

- Guardas de calidad (items_ok < 70% del promedio, etc.) — `run_log` ya guarda los números crudos que Fase 6 va a necesitar, pero la lógica de "fallar el run ruidosamente" no está implementada todavía.
- Workflow de GitHub Actions.
- Adaptador Playwright (no aplica a Chedraui de todos modos).
