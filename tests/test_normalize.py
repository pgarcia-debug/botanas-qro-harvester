"""
Tests de core/normalize.py — sin red, todo cómputo puro.

Los nombres marcados "real" son productos reales del catálogo de Chedraui
(capturados en Fase 3/5). El caso de multipack "N pzas de Xg" NO tiene un
ejemplo real en el catálogo de Chedraui — se prueba con el ejemplo
sintético que el propio brief usa para ilustrar la regla
("12 pzas de 45g"), marcado explícitamente como tal.
"""

from decimal import Decimal

from core.normalize import calc_price_per_100g, resolve_weight


def test_weight_from_package_spec_real():
    # Real: "Botana Papas Sabritas Adobadas 160g", spec de VTEX
    # ("1 pieza de 160g" — matchea el regex de multipack con N=1, que es
    # el comportamiento correcto: un solo regex resuelve ambos casos).
    r = resolve_weight(
        name="Botana Papas Sabritas Adobadas 160g",
        package_content_spec="1 pieza de 160g",
    )
    assert r.net_weight_g == Decimal("160")
    assert r.units_per_pack == 1
    assert r.needs_review is False
    assert r.source == "spec:multipack"


def test_weight_from_package_spec_abbreviated_real():
    # Real: "Mix de Botanas Golden Nuts Dorado 200g", spec abreviada "pz".
    r = resolve_weight(
        name="Mix de Botanas Golden Nuts Dorado 200g",
        package_content_spec="1 pz de 200g",
    )
    assert r.net_weight_g == Decimal("200")
    assert r.needs_review is False


def test_multipack_synthetic_from_brief_example():
    # SINTÉTICO — no hay ejemplo real de este patrón en el catálogo de
    # Chedraui. Se prueba con el ejemplo literal del brief para validar
    # que la regla de multipack "N pzas de Xg" -> total funciona.
    r = resolve_weight(
        name="Sabritas Adobadas 12 pzas de 45g",
        package_content_spec=None,
    )
    assert r.net_weight_g == Decimal("540")  # 12 * 45
    assert r.units_per_pack == 12
    assert r.needs_review is False
    assert r.source == "name:multipack"


def test_multipack_from_spec_field():
    # Multipack declarado en la spec estructurada, no en el nombre.
    r = resolve_weight(
        name="Cacahuates Multipack",
        package_content_spec="6 piezas de 30g",
    )
    assert r.net_weight_g == Decimal("180")  # 6 * 30
    assert r.units_per_pack == 6
    assert r.source == "spec:multipack"


def test_multipack_x_notation():
    r = resolve_weight(name="Botana Barcel 3x40g", package_content_spec=None)
    assert r.net_weight_g == Decimal("120")
    assert r.units_per_pack == 3


def test_simple_weight_from_name_real():
    # Real: "Botana Takis Original 240g" (sin spec disponible).
    r = resolve_weight(name="Botana Takis Original 240g", package_content_spec=None)
    assert r.net_weight_g == Decimal("240")
    assert r.units_per_pack == 1
    assert r.source == "name:simple"


def test_kg_converts_to_grams():
    r = resolve_weight(name="Churros Vitali de Amaranto Chile 500g", package_content_spec="1 pieza de 0.5kg")
    assert r.net_weight_g == Decimal("500")


def test_no_weight_anywhere_needs_review_real():
    # Real: "Frituras De Harina Rincón Tarasco con 10 Piezas" — la spec de
    # este producto no trae gramaje por pieza, solo el conteo. NUNCA se
    # inventa un peso: debe quedar needs_review=True.
    r = resolve_weight(
        name="Frituras De Harina Rincón Tarasco con 10 Piezas",
        package_content_spec=None,
    )
    assert r.net_weight_g is None
    assert r.needs_review is True


def test_bulk_item_from_measurement_unit_real():
    # Real: "Nuez Western Kg" — vendido a granel, sin gramaje en nombre ni
    # spec, pero measurementUnit/unitMultiplier de VTEX sí lo declara.
    r = resolve_weight(
        name="Nuez Western Kg",
        package_content_spec=None,
        measurement_unit="kg",
        unit_multiplier=1.0,
    )
    assert r.net_weight_g == Decimal("1000")
    assert r.needs_review is False
    assert r.source == "platform:kg"


def test_needs_review_when_absolutely_nothing_resolves():
    r = resolve_weight(name="Botana Chechitos Donitas", package_content_spec=None)
    assert r.net_weight_g is None
    assert r.units_per_pack == 1
    assert r.needs_review is True


def test_price_per_100g_basic():
    # Real: SKU 3196352, precio de tienda $61.00, 160g -> $38.125/100g.
    result = calc_price_per_100g(Decimal("61.00"), Decimal("160"))
    assert result == Decimal("38.1250")


def test_price_per_100g_none_when_weight_missing():
    assert calc_price_per_100g(Decimal("38.00"), None) is None


def test_price_per_100g_none_when_price_missing():
    assert calc_price_per_100g(None, Decimal("160")) is None


def test_price_per_100g_never_divides_by_zero_or_negative():
    assert calc_price_per_100g(Decimal("10"), Decimal("0")) is None
    assert calc_price_per_100g(Decimal("10"), Decimal("-5")) is None


def test_price_per_100g_uses_decimal_not_float():
    result = calc_price_per_100g(Decimal("10"), Decimal("3"))
    assert isinstance(result, Decimal)
    # 10/3*100 = 333.333... -> confirma precisión Decimal, no error binario de float
    assert result == Decimal("333.3333")
