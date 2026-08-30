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


def test_plain_rice_excluded_despite_category_fallback():
    # Real: se coló vía el fallback de categoría en una corrida real
    # (~150 productos de arroz/frijol/lenteja simples en "Granos y
    # semillas"). No es botana aunque el retailer lo categorice ahí.
    d = classify("Arroz Chedraui Grano Largo 2.5 Kg", discovery_routes=["categoria"])
    assert not d.include


def test_puffed_rice_snack_still_included():
    d = classify("Botana Bournon Arroz Inflado Queso 81 Gr")
    assert d.include


def test_plain_beans_and_lentils_excluded():
    assert not classify("Frijol Negro Chedraui 900g", discovery_routes=["categoria"]).include
    assert not classify("Lenteja Chedraui 450g", discovery_routes=["categoria"]).include


def test_spicy_garbanzo_included_plain_garbanzo_excluded():
    assert classify("Garbanzo Enchilado kg").include
    assert not classify("Garbanzo La Merced 500g", discovery_routes=["categoria"]).include


def test_raw_popcorn_kernels_excluded_not_ready_to_eat():
    # Real: se coló porque no contenía "semilla" (el filtro anterior solo
    # lo cachaba en ese caso). Maíz palomero crudo = ingrediente, no botana.
    assert not classify("Maíz Palomero Schettino Verde 500g", discovery_routes=["categoria"]).include


def test_birdseed_excluded():
    assert not classify("Alpiste Norver de 500g", discovery_routes=["categoria"]).include


def test_accented_frijol_variant_also_excluded():
    # Real: typo del propio catálogo de Chedraui ("Frijól" con acento) que
    # el regex sin variante acentuada no capturaba.
    assert not classify("Frijól Negro De La Reyna 700g", discovery_routes=["categoria"]).include


def test_dog_treats_excluded_despite_literal_botana_in_name():
    # Real: "Botana" en español también se usa para snacks de mascota —
    # Purina/Dog Chow lo usa literalmente en el nombre del producto.
    assert not classify("Botana Dog Chow Carn Res Poll Salmón").include


def test_refried_beans_excluded_despite_chicharron_flavor_word():
    # Real: "con Chicharrón" es sabor de un platillo enlatado de frijol,
    # no un chicharrón botanero — el include_kw 'chicharr' lo colaba.
    assert not classify("Frijoles Refritos Isadora con Chicharrón 430g", discovery_routes=["categoria"]).include


def test_fried_tomato_sauce_base_excluded():
    assert not classify("Tomates Fritos Caseros LaCuna 560 g", discovery_routes=["categoria"]).include


def test_chicken_nuggets_not_real_popcorn_excluded():
    assert not classify("Palomitas de Pollo Del Día con Salsas Negras 500g", discovery_routes=["categoria"]).include


def test_french_fry_cut_potatoes_excluded():
    assert not classify("Papas a la Francesa Corte Delgado Valley Farms 1Kg", discovery_routes=["categoria"]).include


def test_real_snack_brand_a_la_francesa_style_stays_included():
    # Real: se excluyó por error en una primera pasada — "a la francesa"
    # sin más contexto no basta, esto es un chip real de una marca de
    # botana conocida (Totis), no papa cruda para freír en casa.
    assert classify("Papas Totis Pap's a la Francesa Hot Chili de 70g").include


def test_alubia_beans_excluded():
    assert not classify("Alubia La Merced 500g", discovery_routes=["categoria"]).include


def test_truncated_chocolate_still_excluded():
    # Real: el propio catálogo de Chedraui trunca "Chocolate" a "Chocola"
    # en al menos un producto — el check original solo miraba la palabra
    # completa.
    assert not classify("Platano Dayrise Cubierta Chocola 90g", discovery_routes=["categoria"]).include


def test_grain_and_pantry_imports_excluded():
    for name in [
        "Cous Cous Tipiak Natural 250g",
        "Boulgour Tipiak Precocido 500g",
        "Risotto Cascina Belvedere Espárragos 250g",
        "Basmati Pereg Rice White Gourmet 454g",
        "Elotitos Tiernos San Miguel 220g",
    ]:
        assert not classify(name, discovery_routes=["categoria"]).include


def test_pickles_excluded():
    assert not classify("Pepinillo Van Holtens Jumbo Ajo 209g", discovery_routes=["categoria"]).include


def test_pickle_flavored_snacks_stay_included():
    # Real: se excluyeron por error en una limpieza manual de la base —
    # "pepinillo" como SABOR de un chip/palomita real no es lo mismo que
    # el producto siendo pepinillos encurtidos.
    assert classify("Snack Wavers Pepinillo Picante 127 g").include
    assert classify("Papas Pringles Pepinillo Ranch 155g").include
    assert classify("Palomitas Khloud Pepinillo").include


def test_category_amplia_route_never_gets_fallback_trust():
    # A diferencia de "categoria", "categoria_amplia" (categorías
    # ruidosas como Granos y semillas) nunca activa el fallback de
    # confianza — un nombre ambiguo sin keyword propia se excluye.
    d = classify("Producto Ambiguo Sin Keyword 500g", discovery_routes=["categoria_amplia"])
    assert not d.include


def test_bulk_chicharron_included_despite_internal_brand_label():
    # Se excluyó por error al probar una regla basada en la marca interna
    # "Productos Frescos" — esa marca también cubre chicharrón/nueces a
    # granel legítimos, no solo perecederos.
    assert classify("Chicharrón Prensado Cerdo por kg").include
