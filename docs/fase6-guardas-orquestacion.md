# Fase 6 — Orquestación y guardas de calidad

## Qué se construyó

- [core/quality_guards.py](../core/quality_guards.py) — las 6 guardas del brief, cada una devolviendo un `GuardResult` (pasa/falla, bloqueante o no, mensaje legible).
- [core/vtex.py](../core/vtex.py) — se agregó `RequestStats` (cuenta cada intento de request y cuántos fueron 403/429), compartido entre `resolve_region`/`discover`/`fetch` de un mismo run.
- [core/pipeline.py](../core/pipeline.py) — ahora captura `previous_product_count` **antes** de tocar `products` (línea base para "SKUs desaparecidos"), corre las 6 guardas al final, y decide `status = 'warning'` en `run_log` si alguna guarda bloqueante falló.
- [run.py](../run.py) — entrypoint CLI. Corre todos los retailers activos (o uno con `--retailer`), arma el step summary (a `$GITHUB_STEP_SUMMARY` si existe, si no a stdout), y **sale con exit 1** si cualquier retailer falló en la corrida o tuvo una guarda bloqueante fallida.
- [.github/workflows/harvest.yml](../.github/workflows/harvest.yml) — cron `0 12 * * *` UTC (06:00 America/Mexico_City — México no tiene horario de verano desde 2022, así que el cron no necesita ajuste estacional) + `workflow_dispatch` con input opcional `retailer`.

## Las 6 guardas, tal como quedaron

| Guarda | Bloquea el run | Umbral |
|---|---|---|
| `items_ok_vs_promedio` | Sí | `items_ok` < 70% del promedio de los últimos 3 runs *exitosos* de ese retailer |
| `precio_nulo` | Sí | > 30% de productos con `price_sale` nulo o cero |
| `skus_desaparecidos` | Sí | < 60% de los productos previamente conocidos siguieron apareciendo (> 40% desaparecidos) |
| `tasa_403_429` | Sí | > 10% de los intentos de request recibieron 403/429 |
| `needs_review` | Sí | > 20% de productos con gramaje no resuelto |
| `anomalia_variacion_precio_24h` | **No** | Cualquier SKU con `\|precio_ahora - precio_hace_24h\| / precio_hace_24h` > 60% — se lista, no bloquea |

## Dos decisiones de diseño que vale la pena que veas

1. **Bootstrap sin histórico no bloquea.** `items_ok_vs_promedio` necesita 3 runs exitosos previos para tener un promedio confiable — si no los hay (proyecto recién arrancado, o un retailer nuevo), la guarda pasa automáticamente con la nota "sin suficiente histórico". Mismo criterio para `skus_desaparecidos` en la primera corrida de un retailer (`previous_product_count == 0`). Sin esto, cualquier retailer nuevo fallaría su primer run por definición — lo probé contra el Supabase real: con solo 2 runs históricos (el smoke test de Fase 5), la guarda correctamente dice "no evaluable todavía" en vez de fallar con datos insuficientes.
2. **`RequestStats` cuenta cada intento, no solo el resultado final.** Si una request se reintenta 3 veces por 429 y a la cuarta pasa, cuentan los 3 fallos igual — la guarda mide cuánto está empujando el servidor hacia atrás, no si el retry logró colarla. Si no hiciera esto, un retailer con bot-shield agresivo (como VTEX en checkout, ver Fase 2) podría estar recibiendo 30% de 429 y la guarda nunca se enteraría porque el retry "arregla" cada request individual.

## Validación

- 51 tests (11 nuevos de `quality_guards.py`) — los que son lógica pura (`precio_nulo`, `skus_desaparecidos`, `tasa_403_429`, `needs_review`) tienen test unitario. Los dos que necesitan histórico real de Postgres (`items_ok_vs_promedio`, `anomalia_variacion_precio_24h`) **no tienen test unitario** — misma limitación honesta que `core/db.py` en Fase 5 (no hay `DATABASE_URL` en este entorno). Los corrí manualmente contra el Supabase real vía el MCP con los datos del smoke test de Fase 5, y las queries corren limpias y devuelven lo esperado (2 runs históricos → "no evaluable", 0 anomalías de precio porque no hay datos de hace 24h todavía).
- `run.py --help` corre limpio.

## Qué falta para que esto corra de verdad en producción

1. **Secret `DATABASE_URL` en GitHub Actions** (Settings → Secrets → Actions) — connection string de Postgres del proyecto Supabase, modo *pooler*. Sin esto el workflow va a fallar en el primer paso.
2. El repo necesita estar en GitHub con este workflow para que el cron dispare — ahora mismo el repo es solo local (`git init`, sin remoto, sin commits). Esto es una decisión tuya, no la tomo sola.
3. Primera corrida real recomendable **manual** (`workflow_dispatch` con `retailer=chedraui`) antes de confiar en el cron — para ver el step summary con datos de verdad y confirmar que las guardas se comportan como esperás con el catálogo completo (1,370 SKUs), no solo con los 9 del smoke test.
