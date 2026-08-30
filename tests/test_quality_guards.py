"""
Tests de las guardas de core/quality_guards.py que son lógica pura (no
requieren un pool de Postgres real). Las guardas que sí necesitan
histórico de DB (items_ok_vs_promedio, anomalía de precio 24h) no tienen
test unitario aquí — misma limitación honesta que core/db.py (Fase 5):
se probaron manualmente contra el Supabase real, no con asyncpg mockeado.
"""

from core.quality_guards import (
    RunMetrics,
    check_blocked_rate,
    check_needs_review_rate,
    check_null_price_rate,
    check_skus_disappeared,
)


def _metrics(**overrides) -> RunMetrics:
    base = dict(
        retailer_id=1,
        run_id=1,
        items_ok=100,
        items_err=0,
        needs_review=0,
        null_price=0,
        previous_product_count=100,
        blocked_rate=0.0,
    )
    base.update(overrides)
    return RunMetrics(**base)


def test_null_price_rate_passes_under_threshold():
    m = _metrics(items_ok=100, null_price=29)
    r = check_null_price_rate(m)
    assert r.passed
    assert r.is_blocking


def test_null_price_rate_fails_over_threshold():
    m = _metrics(items_ok=100, null_price=31)
    r = check_null_price_rate(m)
    assert not r.passed


def test_null_price_rate_at_exact_boundary_passes():
    m = _metrics(items_ok=100, null_price=30)
    assert check_null_price_rate(m).passed  # 30% exacto, el límite es "> 30%"


def test_skus_disappeared_fails_when_more_than_40pct_gone():
    m = _metrics(previous_product_count=100, items_ok=59)  # 41% desaparecidos
    r = check_skus_disappeared(m)
    assert not r.passed


def test_skus_disappeared_passes_when_within_limit():
    m = _metrics(previous_product_count=100, items_ok=61)  # 39% desaparecidos
    assert check_skus_disappeared(m).passed


def test_skus_disappeared_skipped_on_first_run():
    m = _metrics(previous_product_count=0, items_ok=5)
    r = check_skus_disappeared(m)
    assert r.passed  # sin histórico, no se puede evaluar — no bloquea


def test_blocked_rate_fails_over_10pct():
    m = _metrics(blocked_rate=0.15)
    assert not check_blocked_rate(m).passed


def test_blocked_rate_passes_under_10pct():
    m = _metrics(blocked_rate=0.05)
    assert check_blocked_rate(m).passed


def test_needs_review_fails_over_20pct():
    m = _metrics(items_ok=100, needs_review=25)
    assert not check_needs_review_rate(m).passed


def test_needs_review_passes_under_20pct():
    m = _metrics(items_ok=100, needs_review=15)
    assert check_needs_review_rate(m).passed


def test_needs_review_with_zero_items_ok_is_worst_case_fails():
    m = _metrics(items_ok=0, needs_review=0)
    assert not check_needs_review_rate(m).passed
