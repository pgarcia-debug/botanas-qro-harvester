"""
Orquestador: llama resolve_region -> discover -> scope_filter -> fetch ->
parse -> diff append-only -> persistencia -> guardas de calidad, para un
retailer.

No sabe qué plataforma es — usa el registro PLATFORM_ADAPTERS para
despachar. Agregar una plataforma nueva = agregar una entrada aquí +
core/<plataforma>.py; agregar un retailer nuevo = un YAML, cero código
(ver CLAUDE.md).

Este módulo decide QUÉ pasó en el run (números, guardas evaluadas). NO
decide si eso hace fallar el proceso — esa decisión (exit code, step
summary de GitHub Actions) es de run.py, para mantener esto reutilizable
fuera de CI también.
"""

from __future__ import annotations

import logging

from core import db, quality_guards, scope_filter, vtex
from core.config import RetailerConfig

logger = logging.getLogger(__name__)

PLATFORM_ADAPTERS = {
    "VTEX": vtex,
}


async def run_retailer(config: RetailerConfig) -> dict:
    """Corre el pipeline completo para un retailer. Devuelve un resumen
    con los números crudos y el resultado de las guardas de calidad de
    Fase 6 — listo para que run.py decida el exit code y arme el step
    summary."""
    adapter = PLATFORM_ADAPTERS.get(config.platform)
    if adapter is None:
        raise ValueError(f"Plataforma sin adaptador registrado: {config.platform}")

    pool = await db.get_pool()
    client = adapter.make_client(config)
    stats = vtex.RequestStats()
    run_id = None
    try:
        async with client:
            region = await adapter.resolve_region(client, config, stats=stats)
            retailer_id = await db.upsert_retailer(
                pool, config.name, config.domain, config.platform, region.platform_data
            )

            # Se captura ANTES de tocar products — es la línea base contra
            # la que se mide "SKUs desaparecidos" (guarda de Fase 6).
            previous_product_count = await quality_guards.get_previous_product_count(pool, retailer_id)

            run_id = await db.start_run_log(pool, retailer_id)

            sku_refs = await adapter.discover(client, config, region, stats=stats)

            in_scope = []
            excluded_count = 0
            for ref in sku_refs:
                decision = scope_filter.classify(ref.name, ref.discovery_routes)
                if decision.include:
                    in_scope.append(ref)
                else:
                    excluded_count += 1

            raw = await adapter.fetch(client, config, region, in_scope, stats=stats)
            products = adapter.parse(raw, config)

            items_ok = 0
            price_events_inserted = 0
            needs_review_count = 0
            null_price_count = 0
            for product in products:
                product_id = await db.upsert_product(pool, retailer_id, product)
                last = await db.get_last_price_event(pool, product_id, product.seller)
                if db.price_changed(last, product):
                    await db.insert_price_event(pool, product_id, product)
                    price_events_inserted += 1
                items_ok += 1
                if product.needs_review:
                    needs_review_count += 1
                if product.price_sale is None or product.price_sale == 0:
                    null_price_count += 1

            items_err = len(in_scope) - len(products)

            metrics = quality_guards.RunMetrics(
                retailer_id=retailer_id,
                run_id=run_id,
                items_ok=items_ok,
                items_err=items_err,
                needs_review=needs_review_count,
                null_price=null_price_count,
                previous_product_count=previous_product_count,
                blocked_rate=stats.blocked_rate,
            )
            guard_results = await quality_guards.evaluate_all(pool, metrics)
            guards_failed = quality_guards.any_blocking_failure(guard_results)

            notes = (
                f"descubiertos={len(sku_refs)} en_alcance={len(in_scope)} "
                f"excluidos_por_scope={excluded_count} items_ok={items_ok} "
                f"items_err={items_err} price_events_nuevos={price_events_inserted} "
                f"needs_review={needs_review_count} precio_nulo={null_price_count} "
                f"tasa_403_429={stats.blocked_rate:.1%} "
                f"guardas={'FALLIDAS' if guards_failed else 'OK'}"
            )
            final_status = "warning" if guards_failed else "success"
            await db.finish_run_log(pool, run_id, items_ok, items_err, final_status, notes)

            return {
                "retailer_id": retailer_id,
                "run_id": run_id,
                "retailer_name": config.name,
                "discovered": len(sku_refs),
                "in_scope": len(in_scope),
                "excluded_by_scope": excluded_count,
                "items_ok": items_ok,
                "items_err": items_err,
                "price_events_inserted": price_events_inserted,
                "needs_review": needs_review_count,
                "null_price": null_price_count,
                "blocked_rate": stats.blocked_rate,
                "previous_product_count": previous_product_count,
                "guard_results": guard_results,
                "guards_failed": guards_failed,
                "status": final_status,
            }
    except Exception as exc:
        logger.exception("Run falló para %s", config.name)
        if run_id is not None:
            await db.finish_run_log(pool, run_id, 0, 0, "failed", str(exc))
        raise
    finally:
        await pool.close()
