"""
Guardas de calidad — Fase 6, el requisito más importante del proyecto
(CLAUDE.md): el modo de falla real no es el crash, es el scraper que
devuelve vacío en silencio. Estas guardas hacen ruido cuando eso pasa.

Cinco guardas FALLAN el run (exit != 0):
  1. items_ok < 70% del promedio de los últimos 3 runs exitosos.
  2. > 30% de productos con precio nulo o cero.
  3. > 40% de SKUs desaparecidos vs. el run anterior.
  4. Tasa de 403/429 > 10%.
  5. > 20% de registros en needs_review por gramaje no resuelto.

Una NO falla el run, se marca como anomalía para revisión manual:
  6. Precio de un SKU con variación > 60% en 24h.

Todas requieren contexto histórico (run_log/products/price_events), por
eso viven separadas del cómputo puro de core/vtex.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import asyncpg


@dataclass
class GuardResult:
    name: str
    passed: bool
    message: str
    is_blocking: bool = True  # False = anomalía, no bloquea el run
    details: dict = field(default_factory=dict)


@dataclass
class RunMetrics:
    """Lo que pipeline.run_retailer() ya calcula, empaquetado para pasarle
    a las guardas sin que quality_guards.py tenga que recalcular nada."""

    retailer_id: int
    run_id: int
    items_ok: int
    items_err: int
    needs_review: int
    null_price: int
    previous_product_count: int
    blocked_rate: float  # de vtex.RequestStats.blocked_rate


async def get_previous_product_count(pool: asyncpg.Pool, retailer_id: int) -> int:
    """Cuántos productos se conocían de este retailer ANTES de este run —
    llamar antes de correr discover()/fetch(), no después (upsert_product
    ya habrá tocado la tabla)."""
    row = await pool.fetchrow("select count(*) as n from products where retailer_id = $1", retailer_id)
    return row["n"]


async def _avg_items_ok_last_n_successful_runs(
    pool: asyncpg.Pool, retailer_id: int, exclude_run_id: int, n: int = 3
) -> Optional[float]:
    rows = await pool.fetch(
        """
        select items_ok from run_log
        where retailer_id = $1 and status = 'success' and id != $2
        order by started_at desc
        limit $3
        """,
        retailer_id,
        exclude_run_id,
        n,
    )
    if len(rows) < n:
        return None  # todavía no hay suficiente histórico — no se puede evaluar esta guarda con confianza
    values = [r["items_ok"] for r in rows]
    return sum(values) / len(values)


async def check_items_ok_vs_average(pool: asyncpg.Pool, m: RunMetrics) -> GuardResult:
    avg = await _avg_items_ok_last_n_successful_runs(pool, m.retailer_id, m.run_id)
    if avg is None:
        return GuardResult(
            "items_ok_vs_promedio", True,
            "sin suficiente histórico (menos de 3 runs exitosos previos) — guarda no evaluable todavía",
            details={"items_ok": m.items_ok},
        )
    threshold = avg * 0.7
    passed = m.items_ok >= threshold
    return GuardResult(
        "items_ok_vs_promedio",
        passed,
        f"items_ok={m.items_ok} vs. 70% del promedio de los últimos 3 runs exitosos ({threshold:.1f}, promedio={avg:.1f})",
        details={"items_ok": m.items_ok, "avg_last_3": avg, "threshold": threshold},
    )


def check_null_price_rate(m: RunMetrics) -> GuardResult:
    if m.items_ok == 0:
        rate = 1.0
    else:
        rate = m.null_price / m.items_ok
    passed = rate <= 0.30
    return GuardResult(
        "precio_nulo",
        passed,
        f"{m.null_price}/{m.items_ok} productos con precio nulo o cero ({rate:.1%}) — límite 30%",
        details={"null_price": m.null_price, "items_ok": m.items_ok, "rate": rate},
    )


def check_skus_disappeared(m: RunMetrics) -> GuardResult:
    if m.previous_product_count == 0:
        return GuardResult(
            "skus_desaparecidos", True,
            "sin histórico previo de productos para este retailer — primera corrida, guarda no aplica",
            details={"previous": 0, "current": m.items_ok},
        )
    rate_present = m.items_ok / m.previous_product_count
    passed = rate_present >= 0.60  # <40% desaparecidos == >=60% siguen presentes
    return GuardResult(
        "skus_desaparecidos",
        passed,
        f"{m.items_ok}/{m.previous_product_count} SKUs previamente conocidos siguieron apareciendo ({rate_present:.1%}) — límite: no más de 40% desaparecidos",
        details={"previous": m.previous_product_count, "current": m.items_ok, "rate_present": rate_present},
    )


def check_blocked_rate(m: RunMetrics) -> GuardResult:
    passed = m.blocked_rate <= 0.10
    return GuardResult(
        "tasa_403_429",
        passed,
        f"tasa de 403/429 = {m.blocked_rate:.1%} — límite 10%",
        details={"blocked_rate": m.blocked_rate},
    )


def check_needs_review_rate(m: RunMetrics) -> GuardResult:
    if m.items_ok == 0:
        rate = 1.0
    else:
        rate = m.needs_review / m.items_ok
    passed = rate <= 0.20
    return GuardResult(
        "needs_review",
        passed,
        f"{m.needs_review}/{m.items_ok} productos con gramaje no resuelto ({rate:.1%}) — límite 20%",
        details={"needs_review": m.needs_review, "items_ok": m.items_ok, "rate": rate},
    )


async def check_price_anomalies_24h(pool: asyncpg.Pool, retailer_id: int) -> GuardResult:
    """NO bloquea el run — solo reporta. Compara el price_event más
    reciente de cada SKU contra el de ~24h antes; si varió >60%, se lista
    como anomalía para revisión manual."""
    rows = await pool.fetch(
        """
        with latest as (
            select distinct on (product_id, seller) product_id, seller, price_sale, captured_at
            from price_events
            where price_sale is not null
            order by product_id, seller, captured_at desc
        ),
        day_ago as (
            select distinct on (pe.product_id, pe.seller) pe.product_id, pe.seller, pe.price_sale, pe.captured_at
            from price_events pe
            where pe.price_sale is not null
              and pe.captured_at <= now() - interval '24 hours'
            order by pe.product_id, pe.seller, pe.captured_at desc
        )
        select l.product_id, l.seller, d.price_sale as price_24h_ago, l.price_sale as price_now, p.name, p.sku
        from latest l
        join day_ago d on d.product_id = l.product_id and d.seller is not distinct from l.seller
        join products p on p.id = l.product_id
        where p.retailer_id = $1
          and d.price_sale > 0
          and abs(l.price_sale - d.price_sale) / d.price_sale > 0.60
        """,
        retailer_id,
    )
    anomalies = [
        {
            "sku": r["sku"],
            "name": r["name"],
            "price_24h_ago": str(r["price_24h_ago"]),
            "price_now": str(r["price_now"]),
            "change_pct": float(abs(r["price_now"] - r["price_24h_ago"]) / r["price_24h_ago"]) * 100,
        }
        for r in rows
    ]
    return GuardResult(
        "anomalia_variacion_precio_24h",
        True,  # nunca bloquea
        f"{len(anomalies)} SKU(s) con variación de precio > 60% en 24h — revisión manual, no bloquea el run",
        is_blocking=False,
        details={"anomalies": anomalies},
    )


async def evaluate_all(pool: asyncpg.Pool, m: RunMetrics) -> list[GuardResult]:
    return [
        await check_items_ok_vs_average(pool, m),
        check_null_price_rate(m),
        check_skus_disappeared(m),
        check_blocked_rate(m),
        check_needs_review_rate(m),
        await check_price_anomalies_24h(pool, m.retailer_id),
    ]


def any_blocking_failure(results: list[GuardResult]) -> bool:
    return any(not r.passed and r.is_blocking for r in results)
