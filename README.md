# Harvester de precios de botanas — retail MX, Querétaro

Extrae el catálogo de botanas saladas y frituras de supermercados con
presencia en Querétaro capital (CP de referencia 76000) y persiste
catálogo + histórico de precios en Postgres (Supabase). Corre 1 vez al
día vía GitHub Actions.

El contrato de arquitectura completo (por qué está diseñado así, qué NO
se puede romper) vive en [CLAUDE.md](CLAUDE.md) — léelo antes de tocar
`core/`. Cada fase del proyecto tiene su propio reporte en [docs/](docs/).

## Quickstart

```bash
pip install -r requirements.txt
```

Variable de entorno requerida para correr el pipeline de verdad (no para
los tests, que nunca tocan la red ni la DB):

```bash
export DATABASE_URL="postgresql://...."   # connection string de Postgres del proyecto Supabase, modo pooler
```

Nunca lo pongas en un archivo del repo — ver `CLAUDE.md`, secretos solo
por variable de entorno.

## Correr

```bash
python run.py                       # todos los retailers activos en retailers/*.yaml
python run.py --retailer chedraui   # solo uno
```

Con `make` (Linux/Mac, o Windows con `make` instalado — en Git Bash sin
`make` corré el `python run.py` de arriba directo):

```bash
make run
make backfill RETAILER=chedraui     # carga inicial de un retailer nuevo
```

Exit code `0` = todo bien. `1` = algún retailer falló la corrida o alguna
guarda de calidad bloqueante disparó — ver la sección de guardas abajo.
El resumen legible se imprime a stdout (o al step summary de GitHub
Actions si corre ahí).

## Tests

```bash
pytest
```

51 tests, todos sin red — usan fixtures JSON reales capturadas de Chedraui
en `tests/fixtures/`. Si agregás un adaptador o cambiás `core/normalize.py`
o `core/scope_filter.py`, agregá el caso a los tests existentes con un
nombre real del catálogo, no uno inventado — es la convención que se usó
en todo el proyecto (ver los comentarios de cada test).

## Agregar un retailer nuevo

**Si ya hay adaptador para su plataforma (hoy: VTEX):** agregar un archivo
`retailers/<nombre>.yaml`. Cero código nuevo — es el principio rector del
proyecto (`CLAUDE.md`).

1. Corré `tools/fingerprint.py <dominio>` para confirmar la plataforma
   (ver `docs/fase1-fingerprint.md` para cómo se hizo con la lista
   original).
2. Resolvé la región para tu CP de referencia — para VTEX,
   `GET /api/checkout/pub/regions?country=MEX&postalCode=<CP>&sc=1` — y
   **validalo contra el navegador real** (3 SKUs conocidos, comparar
   precio del pipeline vs. precio en pantalla con el CP puesto). Ver
   `docs/fase2-regionalizacion-chedraui.md` para el procedimiento
   completo — este paso no es opcional, un CP mal resuelto contamina
   todo el histórico.
3. Descubrí las rutas de categoría reales (`fq=C:<path completo desde el
   departamento raíz>`, no el id de hoja solo) y armá la lista de marcas
   semilla. Corré el descubrimiento y revisá una muestra de 20 productos
   a mano antes de confiar en el scope — `core/scope_filter.py` ya trae
   las reglas genéricas (dulces, condimentos, fruta deshidratada simple,
   etc.) pero cada retailer puede tener sorpresas propias (ver
   `docs/fase3-descubrimiento-chedraui.md` para los falsos positivos que
   aparecieron con Chedraui: un set de Lego, una máquina de palomitas,
   pasta sabor Cheetos...).
4. Escribí el YAML (copiá `retailers/chedraui.yaml` como plantilla).
5. `python run.py --retailer <nombre>` y revisá el resumen.

**Si la plataforma es nueva** (Shopify, custom): eso sí es código nuevo —
un `core/<plataforma>.py` que implemente las mismas 4 funciones que
`core/vtex.py` (`resolve_region`, `discover`, `fetch`, `parse`) y se
registre en `PLATFORM_ADAPTERS` en `core/pipeline.py`. `core/scope_filter.py`
y `core/normalize.py` se reusan tal cual — son lógica de proyecto, no de
plataforma.

## Cómo leer `run_log`

```sql
select retailer_id, started_at, status, items_ok, items_err, notes
from run_log
order by started_at desc
limit 10;
```

`notes` trae un resumen de una línea con todos los números del run
(descubiertos, en alcance, needs_review, tasa de 403/429, si las guardas
fallaron). `status` es `'success'` (todo bien), `'warning'` (corrió pero
alguna guarda de calidad bloqueante falló) o `'failed'` (excepción antes
de terminar).

## Guardas de calidad

Ver [docs/fase6-guardas-orquestacion.md](docs/fase6-guardas-orquestacion.md)
para el detalle de las 6 guardas y por qué están diseñadas así. Resumen:
5 bloquean el run (`items_ok` cae, precio nulo, SKUs desaparecidos, tasa
de bloqueo del retailer, gramaje sin resolver), 1 solo marca una anomalía
sin bloquear (variación de precio > 60% en 24h).

## Re-validar el contexto de región

Si un retailer VTEX empieza a devolver precios que no coinciden con lo
que ves en el navegador, repetí la validación de Fase 2:

1. Abrí el sitio en el navegador, poné el CP de referencia, anotá el
   precio real de 2-3 SKUs conocidos.
2. Compará contra `core.vtex.fetch()` para esos mismos SKUs (podés usar
   `scripts/smoke_test_discover_fetch.py` como plantilla — apuntalo al
   retailer y CP que quieras probar).
3. Si no coinciden: el `regionId`/seller que se está resolviendo cambió
   (Chedraui, por ejemplo, tiene más de un seller cubriendo algunos CPs —
   ver el hallazgo de la tienda "GDL" cubriendo Querétaro en
   `docs/fase2-regionalizacion-chedraui.md`). Repetí el paso 2 de "Agregar
   un retailer nuevo" arriba.

## Consultas útiles

**Precio vigente por marca/presentación, con desglose por retailer,
ordenado por mejor $/100g:**

```sql
select brand, nombre_muestra, net_weight_g, por_retailer, mejor_price_per_100g
from v_current_price_by_gtin
order by mejor_price_per_100g
limit 50;
```

`por_retailer` es jsonb (una key por cadena — se comporta como "columna
por retailer" sin tener que hardcodear nombres de columna; ver
`migrations/0003_views.sql` para por qué se hizo así). Para leer un
retailer específico: `por_retailer->'Chedraui'->>'price_sale'`.

**Top 30 movimientos de precio de los últimos 7 días:**

```sql
select * from v_price_movements_7d limit 30;
```

## Estructura

```
core/
  models.py         # Product, SkuRef, RegionContext, RawPayload (pydantic)
  config.py          # carga retailers/<nombre>.yaml -> RetailerConfig
  normalize.py        # gramaje y price_per_100g — Decimal, nunca inventa un peso
  scope_filter.py      # ¿esto es una "botana"? — lógica de proyecto, no de plataforma
  vtex.py               # adaptador VTEX
  db.py                  # persistencia Postgres
  pipeline.py              # orquestador
  quality_guards.py         # las 6 guardas de Fase 6
retailers/<nombre>.yaml   # config declarativa
migrations/                # SQL versionado
tests/fixtures/              # payloads JSON reales — los tests nunca tocan la red
tools/                        # fingerprint.py y las herramientas exploratorias de Fase 1/3
scripts/                       # utilidades puntuales (smoke tests) — no es el pipeline de producción
run.py                          # entrypoint CLI / GitHub Actions
.github/workflows/harvest.yml    # cron diario + dispatch manual
```

## Estado del proyecto / lo que falta

- Corre con Chedraui únicamente (VTEX). Diseñado para más retailers/CPs
  sin rediseño — ver `CLAUDE.md`.
- `core/db.py` (asyncpg) ya corrió de verdad contra el Supabase real
  (`python run.py --retailer chedraui`, catálogo completo: 1642 productos
  en alcance, 0 errores, todas las guardas pasaron) — ver
  `docs/fase5-adaptador-vtex.md`. Si usás el connection string tipo
  *Transaction pooler* de Supabase (puerto 6543, el que recomienda por
  default), `get_pool()` ya necesita `statement_cache_size=0` — ya está
  así en el código, pero si algún día cambiás a *Session pooler* (puerto
  5432) o a una conexión directa, ese parámetro deja de ser necesario
  (no hace daño dejarlo).
- El repo es solo local todavía (sin remoto, sin commits) — el workflow
  de GitHub Actions no va a disparar hasta que esto esté en GitHub con el
  secret `DATABASE_URL` configurado.
- Fase 7 (adaptador Playwright) no se construyó — no aplica a Chedraui,
  que es 100% API. Si se agrega un retailer que de verdad lo necesite,
  documentar en el código por qué las rutas 1 y 2 (JSON / HTML embebido)
  fueron descartadas para ese caso específico, como manda `CLAUDE.md`.
