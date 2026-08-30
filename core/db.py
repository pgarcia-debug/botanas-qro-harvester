"""
Persistencia en Postgres (Supabase). Todo vía variables de entorno —
`DATABASE_URL` (connection string directo de Postgres, NO la REST API de
Supabase) — nunca hardcoded, ver CLAUDE.md.

Sin ORM: el esquema es chico y estable (Fase 4), SQL explícito es más
fácil de auditar que una capa de abstracción genérica.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import asyncpg

from core.models import Product


async def get_pool() -> asyncpg.Pool:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "Falta la variable de entorno DATABASE_URL (connection string de Postgres). "
            "Nunca hardcodear secretos — ver CLAUDE.md."
        )
    # statement_cache_size=0: el connection string recomendado de Supabase
    # (Transaction pooler, PgBouncer en pool_mode=transaction) NO soporta
    # prepared statements — asyncpg los usa por default y revienta con
    # "DuplicatePreparedStatementError" en cuanto una conexión física del
    # pool se reutiliza para una sesión lógica distinta. Confirmado
    # corriendo el pipeline real contra Supabase (Fase 5/6). Con el
    # Session pooler (puerto 5432) esto no haría falta, pero Transaction
    # pooler es el que Supabase recomienda para scripts de corta duración
    # como este.
    return await asyncpg.create_pool(dsn, min_size=1, max_size=5, statement_cache_size=0)


async def upsert_retailer(
    pool: asyncpg.Pool, name: str, domain: str, platform: str, region_context: dict[str, Any]
) -> int:
    row = await pool.fetchrow(
        """
        insert into retailers (name, domain, platform, region_context)
        values ($1, $2, $3, $4::jsonb)
        on conflict (domain) do update set
            name = excluded.name,
            platform = excluded.platform,
            region_context = excluded.region_context,
            updated_at = now()
        returning id
        """,
        name,
        domain,
        platform,
        json.dumps(region_context),
    )
    return row["id"]


async def upsert_product(pool: asyncpg.Pool, retailer_id: int, product: Product) -> int:
    row = await pool.fetchrow(
        """
        insert into products (
            retailer_id, sku, gtin, name, brand, manufacturer, category_path,
            net_weight_g, package_type, units_per_pack, needs_review, url, image_url,
            last_seen_at
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13, now())
        on conflict (retailer_id, sku) do update set
            gtin = excluded.gtin,
            name = excluded.name,
            brand = excluded.brand,
            manufacturer = excluded.manufacturer,
            category_path = excluded.category_path,
            net_weight_g = excluded.net_weight_g,
            package_type = excluded.package_type,
            units_per_pack = excluded.units_per_pack,
            needs_review = excluded.needs_review,
            url = excluded.url,
            image_url = excluded.image_url,
            last_seen_at = now()
        returning id
        """,
        retailer_id,
        product.sku,
        product.gtin,
        product.name,
        product.brand,
        product.manufacturer,
        product.category_path,
        product.net_weight_g,
        product.package_type,
        product.units_per_pack,
        product.needs_review,
        product.url,
        product.image_url,
    )
    return row["id"]


async def get_last_price_event(
    pool: asyncpg.Pool, product_id: int, seller: Optional[str]
) -> Optional[asyncpg.Record]:
    """Último evento de precio para (product_id, seller) — la unidad de
    diff correcta, no solo product_id (ver CLAUDE.md: seller distingue la
    tienda/región real, necesario para multi-CP a futuro)."""
    return await pool.fetchrow(
        """
        select price_list, price_sale, in_stock
        from price_events
        where product_id = $1 and seller is not distinct from $2
        order by captured_at desc
        limit 1
        """,
        product_id,
        seller,
    )


def price_changed(last: Optional[asyncpg.Record], product: Product) -> bool:
    """Regla de diff append-only de CLAUDE.md: insertar SOLO si cambió
    price_list, price_sale o in_stock respecto al último evento."""
    if last is None:
        return True
    return (
        last["price_list"] != product.price_list
        or last["price_sale"] != product.price_sale
        or last["in_stock"] != product.in_stock
    )


async def insert_price_event(pool: asyncpg.Pool, product_id: int, product: Product) -> None:
    await pool.execute(
        """
        insert into price_events (
            product_id, price_list, price_sale, price_per_100g, currency,
            in_stock, promo_label, seller, source_postal_code
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
        product_id,
        product.price_list,
        product.price_sale,
        product.price_per_100g,
        product.currency,
        product.in_stock,
        product.promo_label,
        product.seller,
        product.source_postal_code,
    )


async def start_run_log(pool: asyncpg.Pool, retailer_id: int) -> int:
    row = await pool.fetchrow(
        "insert into run_log (retailer_id, status) values ($1, 'running') returning id",
        retailer_id,
    )
    return row["id"]


async def finish_run_log(
    pool: asyncpg.Pool, run_id: int, items_ok: int, items_err: int, status: str, notes: str
) -> None:
    await pool.execute(
        """
        update run_log
        set finished_at = now(), items_ok = $2, items_err = $3, status = $4, notes = $5
        where id = $1
        """,
        run_id,
        items_ok,
        items_err,
        status,
        notes,
    )
