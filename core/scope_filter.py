"""
Filtro de alcance de categoría: ¿este producto es una "botana salada o
fritura" según el alcance del proyecto (CLAUDE.md)?

Es lógica de PROYECTO, no de plataforma — un adaptador Shopify futuro
también la usaría tal cual. Por eso vive separada de core/vtex.py: correr
DESPUÉS de discover() (que solo descubre "qué existe"), antes de fetch()
(para no gastar requests de precio en productos fuera de alcance).

Reglas y motivos derivados y auditados en Fase 3 contra el catálogo real
de Chedraui (ver docs/fase3-descubrimiento-chedraui.md) — no son
supuestos, son el resultado de revisar cientos de productos reales y
corregir los falsos positivos/negativos que fue arrojando cada iteración.
Las decisiones de alcance ambiguas (carne seca, pretzels, chía) ya las
resolvió el usuario explícitamente y están codificadas aquí, no como
"pendiente".
"""

from __future__ import annotations

import re
from typing import NamedTuple


class ScopeDecision(NamedTuple):
    include: bool
    reason: str


_INCLUDE_KW = [
    "papa", "papas", "frit", "tortilla", "chip", "churrito", "churro",
    "extrudid", "cacahuate", "cacahuat", "nuez", "nueces", "almendra",
    "pistache", "pistacho", "macadamia", "avellana", "botanera", "semilla",
    "pepita", "chicharr", "palomita", "botana", "tostad", "takis",
    "cheeto", "dorito", "sabrit", "ruffles", "rancherit", "crujito",
    "totopo", "nacho", "tostitos", "charrito", "funyun", "haba", "habas",
    "snack", "jicama", "jícama", "castaña", "castana", "garbanzo", "totis",
]

_STRONG_SNACK_KW = [
    "papa", "chip", "botana", "cacahuate", "cacahuat", "chicharr",
    "totopo", "nacho", "tostad", "jicama", "jícama",
]

_DRIED_FRUIT_SIGNAL_RE = re.compile(
    r"\bpasas?\b|ciruela pasa|arándano|arandano|\bhigo\b|deshidratad|desidratad",
    re.IGNORECASE,
)


def classify(name: str, discovery_routes: list[str] | None = None) -> ScopeDecision:
    """Decide si `name` (nombre de producto tal cual lo da el retailer)
    cae dentro del alcance de "botanas saladas y frituras" del proyecto.
    Devuelve (include, motivo) — el motivo se persiste/loguea siempre,
    para poder auditar decisiones después sin re-ejecutar el filtro.

    `discovery_routes` (de SkuRef.discovery_routes): si el producto vino
    de la ruta de categoría propia del retailer y no dispara ninguna
    exclusión dura arriba, se confía en la categorización del retailer
    por default aunque el nombre no traiga ninguna keyword reconocible
    (ver Fase 3 — 602 productos de Chedraui solo se encontraban así)."""
    n = name.lower()
    discovery_routes = discovery_routes or []

    if n.startswith("salsa ") or n.startswith("dip "):
        return ScopeDecision(False, "condimento/aderezo embotellado, no es la botana en sí")
    if "crema" in n and ("cacahuate" in n or "cacahuat" in n):
        return ScopeDecision(False, "crema/mantequilla de cacahuate (untable), no se come a puños como botana")
    if "palanqueta" in n:
        return ScopeDecision(False, "palanqueta — confitería, no botana salada")
    if n.startswith("barra ") or n.startswith("barras "):
        return ScopeDecision(False, "barra tipo cereal/proteína — excluida explícitamente por el brief")
    if "granola" in n:
        return ScopeDecision(False, "granola — adyacente a 'barras de cereal', excluida")
    if "mccain" in n or ("congelad" in n and "papa" in n):
        return ScopeDecision(False, "papa congelada para cocinar, no lista para comer")
    if re.search(r"\ben salsa (verde|roja|negra)\b", n) and "chicharr" in n:
        return ScopeDecision(False, "platillo preparado/refrigerado, no botana crujiente empacada")
    if "gomita" in n or "chicle" in n or "paleta" in n:
        return ScopeDecision(False, "dulcería/confitería — excluida explícitamente")
    if "galleta" in n:
        return ScopeDecision(False, "galleta — excluida explícitamente aunque el producto base sea palomitas/botana")
    if "obleas" in n:
        return ScopeDecision(False, "oblea de amaranto tipo 'alegría' — confitería")
    if "grano de caf" in n or n.startswith("café ") or "cafe " in n:
        return ScopeDecision(False, "grano de café — no es botana")
    if "dátil" in n or "datil" in n:
        return ScopeDecision(False, "dátil — fruta fresca/deshidratada simple")
    if "yogurt" in n and ("pasa" in n or "arandano" in n or "arándano" in n):
        return ScopeDecision(False, "fruta deshidratada cubierta de yogurt — confitería")
    if "chocolate" in n and not ("palomita" in n or "popcorn" in n):
        return ScopeDecision(False, "cubierto/mezclado con chocolate y el producto base no es palomitas — confitería")
    if re.search(r"\bcacao\b", n):
        return ScopeDecision(False, "cacao crudo/en polvo — ingrediente, no botana")
    if "lego" in n or "maquina de palomitas" in n or "máquina de palomitas" in n:
        return ScopeDecision(False, "juguete/aparato, no un alimento")
    if "pasta" in n and ("cheetos" in n or "macarron" in n or "macarrón" in n):
        return ScopeDecision(False, "pasta seca para cocinar, no lista para comer")

    if _DRIED_FRUIT_SIGNAL_RE.search(n) and not any(k in n for k in _STRONG_SNACK_KW):
        spicy = any(k in n for k in ["enchilad", "chile", "tajin", "tajín", "picante"])
        with_nuts = any(k in n for k in ["nuez", "nueces", "almendra", "pecana", "pistache"])
        if spicy or with_nuts:
            return ScopeDecision(True, "fruta deshidratada preparada tipo botana mexicana o mezclada con nueces")
        return ScopeDecision(False, "fruta deshidratada simple, sin preparación salada")

    if "trail" in n and ("dulce" in n or "choco" in n):
        return ScopeDecision(False, "trail mix explícitamente dulce/chocolatoso")

    # Decisiones de alcance ya resueltas por el usuario en Fase 3 (no son
    # "pendientes" — quedaron como política del proyecto en CLAUDE.md).
    if "pretzel" in n:
        return ScopeDecision(False, "pretzel — fuera de alcance, decisión del usuario en Fase 3")
    if "carne seca" in n or "jerky" in n or "machaca" in n or "jack links" in n or "cecina" in n:
        return ScopeDecision(False, "carne seca/jerky — fuera de alcance, decisión del usuario en Fase 3")
    if "chía" in n or "chia " in n or n.startswith("chia"):
        return ScopeDecision(False, "chía — fuera de alcance, decisión del usuario en Fase 3 (se consume como ingrediente)")

    if "semilla" in n or "semillas" in n:
        if any(k in n for k in ["pasto", "hortaflor", "happy flower", "aves silvestres", "para aves", "marokai", "diseño semillas"]):
            return ScopeDecision(False, "semilla de jardín/pasto o artículo no alimenticio")
        if any(k in n for k in ["linaza", "ajonjol", "comino", "tapioca", "cebada", "quinoa", "alubia", "centeno"]):
            return ScopeDecision(False, "semilla/grano usado como ingrediente de cocina, no se come a puños como botana")
        if any(k in n for k in ["pan ", "miel "]):
            return ScopeDecision(False, "pan multigrano o miel — la palabra 'semillas' solo describe un ingrediente")
        if "verde valle" in n:
            return ScopeDecision(False, "marca de granos/legumbres crudos para cocinar, no botana lista para comer")

    for kw in _INCLUDE_KW:
        if kw in n:
            return ScopeDecision(True, f"keyword de inclusión '{kw}'")

    if "categoria" in discovery_routes:
        return ScopeDecision(
            True,
            "sin keyword propio, pero el retailer ya lo cataloga bajo una categoría de botanas y no disparó ninguna exclusión — confianza baja, auditar",
        )

    return ScopeDecision(False, "no matchea ninguna keyword de inclusión y no viene de la ruta de categoría del retailer")
