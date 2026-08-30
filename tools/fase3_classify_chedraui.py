"""
Fase 3 — Clasificación final del set unificado de Chedraui.

Toma fase3_chedraui_raw.json (salida de fase3_discovery_chedraui.py) y
aplica reglas explícitas de inclusión/exclusión más finas que el filtro de
keyword ingenuo usado durante el descubrimiento — este script documenta
CADA regla con su razonamiento, para que el usuario pueda auditar y
corregir criterios.

No es el pipeline de producción — es la herramienta de curación de Fase 3.
"""

import json
import re

IN_PATH = "fase3_chedraui_raw.json"
OUT_PATH = "fase3_chedraui_classified.json"


INCLUDE_KW = [
    "papa", "papas", "frit", "tortilla", "chip", "churrito", "churro",
    "extrudid", "cacahuate", "cacahuat", "nuez", "nueces", "almendra",
    "pistache", "pistacho", "macadamia", "avellana", "botanera", "semilla",
    "pepita", "chicharr", "palomita", "botana", "tostad", "takis",
    "cheeto", "dorito", "sabrit", "ruffles", "rancherit", "crujito",
    "totopo", "nacho", "tostitos", "charrito", "funyun", "haba", "habas",
    "snack", "jicama", "jícama", "castaña", "castana", "garbanzo", "totis",
]


def classify(name: str, brand: str, routes: list[str]) -> tuple[str, str]:
    """Devuelve (decision, motivo). decision en {INCLUDE, EXCLUDE, REVISAR}."""
    n = name.lower()

    # --- Exclusiones duras: producto NO es una botana lista para comer ---
    # NOTA: se probó excluir en bloque por brand in {"Frutas y Verduras",
    # "Productos Frescos"} (productos vendidos a granel/mostrador fresco).
    # Se revirtió: esa marca interna de Chedraui también cubre chicharrón,
    # nueces y semillas a granel — excluía de golpe cosas como "Chicharrón
    # Botanero Bolsa kg", "Nuez de la India kg", "Pepita Cruda por kg" y
    # hasta productos literalmente llamados "Botana...". La marca NO es
    # una señal confiable de perecedero aquí; se dejan las reglas de
    # keyword/fruta-deshidratada hacer el trabajo caso por caso.
    if n.startswith("salsa ") or n.startswith("dip "):
        return "EXCLUDE", "condimento/aderezo embotellado (Salsa/Dip como sustantivo principal), no es la botana en sí"
    if "crema" in n and ("cacahuate" in n or "cacahuat" in n):
        return "EXCLUDE", "crema/mantequilla de cacahuate (untable de despensa), no se come a puños como botana"
    if "palanqueta" in n:
        return "EXCLUDE", "palanqueta (dulce/turrón de cacahuate prensado con azúcar) — confitería, no botana salada"
    if n.startswith("barra ") or n.startswith("barras "):
        return "EXCLUDE", "barra tipo cereal/proteína — categoría explícitamente excluida por el brief (barras de cereal), se generaliza a barras similares"
    if "granola" in n:
        return "EXCLUDE", "granola — adyacente a 'barras de cereal', categoría excluida por el brief"
    if "mccain" in n or ("congelad" in n and "papa" in n):
        return "EXCLUDE", "papa congelada para cocinar en casa, no lista para comer"
    if re.search(r"\ben salsa (verde|roja|negra)\b", n) and "chicharr" in n:
        return "EXCLUDE", "platillo preparado/refrigerado (chicharrón guisado), no botana crujiente empacada"
    # NOTA: se probó excluir "dona"/"donita" como pan dulce. Se revirtió:
    # en este catálogo "Donita(s)" resultó ser mayormente un snack frito
    # en forma de anillo de marcas de botana reconocidas (p.ej. "Totis
    # Donitas Chile y Limón", "Totis Donitas Sal y Limón" — sabores
    # salados, no dulces), no una dona de pastelería. Se deja pasar a la
    # clasificación normal por keyword/categoría.
    if "gomita" in n or "chicle" in n or "paleta" in n:
        return "EXCLUDE", "dulcería/confitería, categoría explícitamente excluida"
    if "galleta" in n:
        return "EXCLUDE", "galleta (aunque el producto base sea palomitas/botana), categoría explícitamente excluida"
    if "obleas" in n:
        return "EXCLUDE", "oblea (dulce tipo confitería), categoría explícitamente excluida"
    if ("grano de caf" in n) or n.startswith("café ") or "cafe " in n:
        return "EXCLUDE", "grano de café — no es botana, filed bajo Botanas por error de categorización"
    if "dátil" in n or "datil" in n:
        return "EXCLUDE", "dátil = fruta fresca/deshidratada simple, no botana salada"
    if "yogurt" in n and ("pasa" in n or "arandano" in n or "arándano" in n):
        return "EXCLUDE", "fruta deshidratada cubierta de yogurt = confitería, no botana salada"
    if "chocolate" in n and not ("palomita" in n or "popcorn" in n):
        return "EXCLUDE", "cubierto/mezclado con chocolate y el producto base no es palomitas — confitería"
    strong_snack_kw = [
        "papa", "chip", "botana", "cacahuate", "cacahuat", "chicharr",
        "totopo", "nacho", "tostad", "jicama", "jícama",
    ]
    is_dried_fruit_signal = (
        re.search(r"\bpasas?\b", n) or "ciruela pasa" in n
        or ("arándano" in n or "arandano" in n) or "higo" in n
        or "deshidratad" in n or "desidratad" in n
    )
    # Solo se evalúa como "fruta deshidratada simple" si NO trae ya una
    # palabra fuerte de botana (p.ej. "Papas ... Deshidratado" es un chip
    # de papa, no fruta seca — el método de preparación no cambia qué es
    # el producto base).
    if is_dried_fruit_signal and not any(k in n for k in strong_snack_kw):
        # Fruta deshidratada: excluir SALVO que tenga preparación
        # picante/salada tipo botana mexicana (enchilado/chile/tajín) o
        # venga en mezcla con nueces (trail mix nuez-forward).
        spicy = any(k in n for k in ["enchilad", "chile", "tajin", "tajín", "picante"])
        with_nuts = any(k in n for k in ["nuez", "nueces", "almendra", "pecana", "pistache"])
        if spicy or with_nuts:
            return "INCLUDE", "fruta deshidratada preparada tipo botana mexicana (enchilada/con chile) o mezclada con nueces (trail mix)"
        return "EXCLUDE", "fruta deshidratada simple, sin preparación salada — no es botana salada"
    if "trail" in n and ("dulce" in n or "choco" in n):
        return "EXCLUDE", "trail mix explícitamente dulce/chocolatoso, no nuez-forward"
    if "pretzel" in n:
        return "EXCLUDE", "pretzel — decisión explícita del usuario en Fase 3: fuera de alcance, sin excepción"
    if "carne seca" in n or "jerky" in n or "machaca" in n or "jack links" in n or "cecina" in n:
        return "EXCLUDE", "carne seca/jerky — decisión explícita del usuario en Fase 3: fuera de alcance (categoría de producto distinta a fritura/extruido)"
    if "chía" in n or "chia " in n or n.startswith("chia"):
        return "EXCLUDE", "chía — decisión explícita del usuario en Fase 3: se consume como ingrediente, no como botana lista para comer"
    if re.search(r"\bcacao\b", n):
        return "EXCLUDE", "cacao crudo/en polvo — ingrediente, no botana; filed bajo Botanas por error de categorización"
    if "lego" in n or "maquina de palomitas" in n or "máquina de palomitas" in n:
        return "EXCLUDE", "juguete/aparato (set de Lego, máquina de hacer palomitas), no un alimento — filed bajo Botanas por error de categorización"
    if "pasta" in n and ("cheetos" in n or "macarron" in n or "macarrón" in n):
        return "EXCLUDE", "pasta seca para cocinar (macarrón sabor Cheetos), no lista para comer — mismo criterio que la papa congelada McCain"

    # --- Cluster "semillas": el término genérico de Fase 3 resultó muy
    # ruidoso — trae semillas de jardín, especias, granos de cocina,
    # pan multigrano, miel y alimento para aves, todo porque contienen la
    # palabra "semilla(s)". Se filtran con reglas específicas ANTES de que
    # el "semilla" genérico de INCLUDE_KW las acepte de golpe.
    if "semilla" in n or "semillas" in n:
        gardening_or_nonfood = any(k in n for k in [
            "pasto", "hortaflor", "happy flower", "aves silvestres",
            "para aves", "marokai", "diseño semillas",
        ])
        cooking_ingredient = any(k in n for k in [
            "linaza", "ajonjol", "comino", "tapioca", "cebada", "quinoa",
            "alubia", "centeno",
        ])
        bread_or_honey = any(k in n for k in ["pan ", "miel "])
        raw_dry_goods_brand = "verde valle" in n  # marca de granos/legumbres crudos para cocinar, no botanas
        if gardening_or_nonfood:
            return "EXCLUDE", "semilla de jardín/pasto o artículo no alimenticio, no botana — filed bajo Botanas por error de categorización"
        if cooking_ingredient:
            return "EXCLUDE", "semilla/grano usado como ingrediente de cocina (linaza/ajonjolí/comino/tapioca/cebada/quinoa/alubia), no se come a puños como botana"
        if bread_or_honey:
            return "EXCLUDE", "pan multigrano o miel con semillas — no es la categoría botanas, la palabra 'semillas' solo describe un ingrediente"
        if raw_dry_goods_brand:
            return "EXCLUDE", "marca de granos/legumbres crudos para cocinar (Verde Valle), no botana lista para comer"
        # sobrevive todo lo anterior -> semilla comestible tipo botana
        # (girasol, pepita, ajonjolí como topping de botana, mixes de
        # marcas de snack) -> cae al INCLUDE_KW normal más abajo.

    # --- Inclusiones por tipo de producto ---
    for kw in INCLUDE_KW:
        if kw in n:
            return "INCLUDE", f"keyword de inclusión '{kw}'"

    # Si Chedraui ya lo catalogó bajo "Botanas y frutos secos"/"Botanas" y
    # no disparó ninguna regla de exclusión arriba, se acepta con prioridad
    # a su propia categorización — pero se marca como confianza baja para
    # que aparezca en la muestra de validación.
    if "categoria" in routes:
        return "INCLUDE", "sin keyword propio, pero Chedraui ya lo cataloga en Botanas/Botanas y frutos secos y no disparó ninguna exclusión — confianza baja, revisar en la muestra"

    return "REVISAR", "no matchea ninguna regla de inclusión y no viene de la ruta de categoría — revisar manualmente"


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    results = {"INCLUDE": [], "EXCLUDE": [], "REVISAR": []}
    for p in data["products"]:
        decision, reason = classify(p.get("name") or "", p.get("brand") or "", p.get("routes") or [])
        p["decision"] = decision
        p["reason"] = reason
        results[decision].append(p)

    print(f"Total: {len(data['products'])}")
    for k, v in results.items():
        print(f"  {k}: {len(v)}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"Guardado en {OUT_PATH}")


if __name__ == "__main__":
    main()
