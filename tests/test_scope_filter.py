"""
Tests de core/scope_filter.py — todos los casos son nombres reales del
catálogo de Chedraui (Fase 3), elegidos porque cada uno representa una
categoría de falso positivo/negativo real que se encontró y corrigió
durante la curación (ver docs/fase3-descubrimiento-chedraui.md). No son
casos inventados: son regresiones documentadas.
"""

from core.scope_filter import classify


def test_clean_botana_includes():
    assert classify("Botana Sabritas Sabritones Chile y Limón 160g").include
    assert classify("Papas Barcel Chip's Sal de Mar 60g").include
    assert classify("Botana Surtida Sabritas Paketaxo Quexo 208g").include


def test_bottled_sauce_excluded_even_with_botana_flavor_name():
    d = classify("Salsa Chicharrón de Chile Güero El Don 170g")
    assert not d.include
    assert "condimento" in d.reason


def test_peanut_butter_spread_excluded():
    d = classify("Crema de Cacahuate Skippy Cremoso 462g")
    assert not d.include
    assert "untable" in d.reason


def test_plain_dried_fruit_excluded():
    d = classify("Pasas Sun Maid California 6 Piezas")
    assert not d.include


def test_spicy_dried_fruit_included():
    # Distinto del caso anterior: preparación picante mexicana sí cuenta.
    d = classify("Mango Come Verde Enchilado Deshidratado 60g")
    assert d.include


def test_garden_seeds_excluded_not_snack_seeds():
    d = classify("Semillas Pasto Sol y Sombra Hortaflor")
    assert not d.include
    assert "jardín" in d.reason


def test_cooking_seed_excluded():
    d = classify("Quinoa Naturalika Vita Semilla 100g")
    assert not d.include


def test_snack_sunflower_seed_included():
    d = classify("Semilla De Girasol Leo 150g")
    assert d.include


def test_jicama_baked_chips_included():
    # Se excluyó por error en una primera pasada (se asumió "producto
    # fresco de verdulería"); son chips horneados/deshidratados empacados.
    d = classify("Jícama Vitali Horneada Chile 50g")
    assert d.include


def test_ring_shaped_savory_snack_donitas_included():
    # "Donitas" en este catálogo es un snack frito en forma de anillo con
    # sabores salados, no pan dulce.
    d = classify("Totis Donitas Chile y Limón 110g")
    assert d.include


def test_lego_toy_excluded_despite_matching_papas_fritas():
    d = classify("Lego City Camión de Papas Fritas Set 60488")
    assert not d.include


def test_popcorn_machine_appliance_excluded():
    d = classify("Maquina De Palomitas PDH 4 Onzas Roja")
    assert not d.include


def test_cheetos_pasta_excluded_needs_cooking():
    d = classify("Pasta Cheetos Macarron Flamin Hot 160g")
    assert not d.include


def test_frozen_fries_excluded_not_ready_to_eat():
    d = classify("Papas Tradicionales Corte Recto McCain 500g")
    assert not d.include


def test_out_of_scope_decisions_from_fase3_user_call():
    assert not classify("Carne Seca Vik's Jerky con Chile Limón 86g").include
    assert not classify("Pretzel Autenta Foods Horneado 150g").include
    assert not classify("Chía Organica Vivio Foods Semillas 340g").include


def test_chocolate_covered_popcorn_still_included():
    # El producto base es palomitas — el sabor no lo saca de la categoría.
    d = classify("Palomitas Cretors Chocolate Oscuro 156g")
    assert d.include


def test_cookie_popcorn_excluded():
    d = classify("Palomitas Cookie Pop Oreo Galleta 148g")
    assert not d.include


def test_category_route_fallback_trusts_retailer_categorization():
    # Sin keyword propio reconocible, pero descubierto vía la categoría
    # "Botanas" del propio retailer -> se confía por default.
    d = classify("Mix Cosechero Spice 200g", discovery_routes=["categoria"])
    assert d.include
    assert "confianza baja" in d.reason


def test_no_category_route_and_no_keyword_excluded():
    # El mismo tipo de nombre ambiguo, pero encontrado SOLO por
    # full-text/marca (sin el respaldo de la categorización del
    # retailer) -> no se confía a ciegas.
    d = classify("Mix Cosechero Spice 200g", discovery_routes=["texto_libre"])
    assert not d.include


def test_bulk_chicharron_included_despite_internal_brand_label():
    # Se excluyó por error al probar una regla basada en la marca interna
    # "Productos Frescos" — esa marca también cubre chicharrón/nueces a
    # granel legítimos, no solo perecederos.
    assert classify("Chicharrón Prensado Cerdo por kg").include
