"""
Tests de core/vtex.py `parse()` — la única función del adaptador sin I/O.
Usa fixtures JSON reales capturados de Chedraui (Fase 2/3/5), NUNCA toca
la red (CLAUDE.md).

Fixtures:
  - chedraui_search_sample.json: respuesta real de
    /api/catalog_system/pub/products/search para 3 SKUs conocidos.
  - chedraui_simulation_sample.json: respuesta real de
    /api/checkout/pub/orderForms/simulation para esos mismos 3 SKUs,
    CP 76000 — incluye el caso real de precio regional ($61.00, SKU
    3196352) que en Fase 2 se demostró que diverge del precio de la API
    de catálogo ($52.00), y el caso real de un SKU sin stock (3783832).
"""

from decimal import Decimal

from core.models import RawPayload
from core.vtex import _product_to_skuref, parse
from tests.conftest import load_fixture


def _build_raw_payload() -> RawPayload:
    search_results = load_fixture("chedraui_search_sample.json")
    simulation = load_fixture("chedraui_simulation_sample.json")

    sku_refs = []
    for p in search_results:
        ref = _product_to_skuref(p)
        assert ref is not None
        sku_refs.append(ref)

    price_data = {item["id"]: item for item in simulation["items"]}
    return RawPayload(sku_refs=sku_refs, price_data=price_data)


def test_parse_regional_price_matches_fase2_validation(chedraui_config):
    """SKU 3196352: el precio real de tienda validado en Fase 2 es
    $61.00 (vs $52.00 que da la API de catálogo nacional). parse() debe
    usar la fuente correcta (simulation), no inventar ni recalcular."""
    raw = _build_raw_payload()
    products = parse(raw, chedraui_config)
    by_sku = {p.sku: p for p in products}

    p = by_sku["3196352"]
    assert p.price_sale == Decimal("61.00")
    assert p.price_list == Decimal("61.00")
    assert p.in_stock is True
    assert p.seller == "chedrauimx0268"  # el seller regional real, no "1" genérico
    assert p.source_postal_code == "76000"
    # gramaje viene de la spec "Contenido del empaque": "1 pieza de 160g"
    assert p.net_weight_g == Decimal("160")
    assert p.needs_review is False
    assert p.price_per_100g == Decimal("38.1250")  # (61/160)*100


def test_parse_out_of_stock_sku(chedraui_config):
    """SKU 3783832 (Rancheritos): sin stock en la región — confirmado en
    Fase 2 (la página del producto mostraba 'Agotado', sin precio)."""
    raw = _build_raw_payload()
    products = parse(raw, chedraui_config)
    by_sku = {p.sku: p for p in products}
    p = by_sku["3783832"]
    assert p.in_stock is False
    # el precio de lista sigue viniendo (VTEX lo reporta aunque no haya stock)
    assert p.price_list == Decimal("15.00")


def test_parse_gtin_comes_from_item_ean(chedraui_config):
    raw = _build_raw_payload()
    products = parse(raw, chedraui_config)
    by_sku = {p.sku: p for p in products}
    assert by_sku["3104995"].gtin == "7501011167667"
    assert by_sku["3196352"].gtin == "7501011133921"


def test_parse_skips_sku_without_price_data(chedraui_config):
    """Si simulation no devolvió dato para un SKU (falla puntual, SKU
    discontinuado), parse() no debe inventar un Product a medias — el
    pipeline lo cuenta como error, no como producto con precio nulo."""
    search_results = load_fixture("chedraui_search_sample.json")
    sku_refs = [_product_to_skuref(p) for p in search_results]
    raw = RawPayload(sku_refs=sku_refs, price_data={})  # sin datos de precio para nadie
    products = parse(raw, chedraui_config)
    assert products == []


def test_parse_decimal_types_not_float(chedraui_config):
    raw = _build_raw_payload()
    products = parse(raw, chedraui_config)
    for p in products:
        if p.price_list is not None:
            assert isinstance(p.price_list, Decimal)
        if p.price_per_100g is not None:
            assert isinstance(p.price_per_100g, Decimal)
