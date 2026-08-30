"""
Normalización de gramaje y cálculo de price_per_100g.

Lógica de primera clase (CLAUDE.md) — no limpieza cosmética. Regla rectora:
NUNCA se inventa un peso. Si nada de lo de abajo resuelve un gramaje con
confianza, el producto se marca needs_review=True y net_weight_g queda en
None (y por lo tanto price_per_100g también).

Fuentes de gramaje, en orden de confianza (confirmado contra datos reales
de Chedraui en Fase 5 — ver tests/fixtures):

1. Spec estructurada de la plataforma — para VTEX, el campo
   "Contenido del empaque" (p.ej. "1 pieza de 160g", "12 piezas de 45g").
   Es la fuente más confiable: la escribe el retailer, no requiere parsear
   el nombre de marketing. Si trae un conteo > 1, es un multipack — se
   resuelve a gramaje TOTAL (conteo × gramaje por pieza).
2. El mismo patrón "N pieza(s)/pza(s) de Xg", pero buscado en el NOMBRE
   del producto (por si el retailer no manda la spec pero sí lo puso en
   el nombre — éste es el patrón que ejemplifica el brief: "12 pzas de
   45g").
3. Patrón "NxXg" en el nombre (multipack, notación alterna).
4. Peso simple: el ÚLTIMO número seguido de unidad (g/gr/kg) en el
   nombre — patrón dominante en nombres reales tipo
   "Sabritas Adobadas 240g".
5. measurementUnit/unitMultiplier de la propia plataforma — para
   productos vendidos a granel ("por kg"): si measurementUnit == "kg",
   el gramaje es 1000 × unitMultiplier. Señal estructural, no inventada.
6. Nada de lo anterior resolvió -> needs_review=True.

Todo con Decimal. Nunca float — un error de redondeo en dinero no es
aceptable (CLAUDE.md).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple, Optional

_UNIT_WORD = r"(?:pzas?|piezas?|pz)\.?"

# "N pieza(s)/pza(s) de Xg" — captura conteo y gramaje por unidad.
_MULTIPACK_DE_RE = re.compile(
    rf"(\d+)\s*{_UNIT_WORD}\s*de\s*(\d+(?:[.,]\d+)?)\s*(kg|gr|g)\b",
    re.IGNORECASE,
)
# "NxXg" — notación alterna de multipack.
_MULTIPACK_X_RE = re.compile(
    r"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|gr|g)\b",
    re.IGNORECASE,
)
# Peso simple: cualquier "<número><unidad>" — se usa el ÚLTIMO match del
# string, porque el patrón dominante en catálogos reales es
# "<Producto> <sabor/variante> <peso>" con el peso al final.
_WEIGHT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g)\b",
    re.IGNORECASE,
)


class WeightResolution(NamedTuple):
    net_weight_g: Optional[Decimal]
    units_per_pack: int
    needs_review: bool
    source: str  # de dónde salió, para debugging/auditoría — no se persiste


def _to_grams(value: str, unit: str) -> Decimal:
    dec = Decimal(value.replace(",", "."))
    if unit.lower() == "kg":
        return dec * Decimal(1000)
    return dec


def _try_multipack(text: str) -> Optional[tuple[Decimal, int]]:
    m = _MULTIPACK_DE_RE.search(text)
    if not m:
        m = _MULTIPACK_X_RE.search(text)
    if not m:
        return None
    count = int(m.group(1))
    per_unit = _to_grams(m.group(2), m.group(3))
    if count <= 0 or per_unit <= 0:
        return None
    return per_unit * count, count


def _try_simple_weight(text: str) -> Optional[Decimal]:
    matches = list(_WEIGHT_RE.finditer(text))
    if not matches:
        return None
    m = matches[-1]
    grams = _to_grams(m.group(1), m.group(2))
    return grams if grams > 0 else None


def resolve_weight(
    name: str,
    package_content_spec: Optional[str] = None,
    measurement_unit: Optional[str] = None,
    unit_multiplier: Optional[float] = None,
) -> WeightResolution:
    """Resuelve el gramaje de un producto. Ver docstring del módulo para
    el orden de prioridad de las fuentes."""

    # 1. Spec estructurada del retailer.
    if package_content_spec:
        result = _try_multipack(package_content_spec)
        if result:
            total, count = result
            return WeightResolution(total, count, False, "spec:multipack")
        simple = _try_simple_weight(package_content_spec)
        if simple:
            return WeightResolution(simple, 1, False, "spec:simple")

    # 2/3. Multipack en el nombre.
    result = _try_multipack(name)
    if result:
        total, count = result
        return WeightResolution(total, count, False, "name:multipack")

    # 4. Peso simple en el nombre.
    simple = _try_simple_weight(name)
    if simple:
        return WeightResolution(simple, 1, False, "name:simple")

    # 5. measurementUnit/unitMultiplier (venta a granel).
    if measurement_unit and unit_multiplier:
        unit = measurement_unit.lower()
        if unit == "kg":
            return WeightResolution(
                Decimal(str(unit_multiplier)) * Decimal(1000), 1, False, "platform:kg"
            )
        if unit in ("g", "gr"):
            return WeightResolution(
                Decimal(str(unit_multiplier)), 1, False, "platform:g"
            )

    # 6. No se pudo resolver — NUNCA se inventa un peso.
    return WeightResolution(None, 1, True, "unresolved")


def calc_price_per_100g(
    price: Optional[Decimal], net_weight_g: Optional[Decimal]
) -> Optional[Decimal]:
    """price ya en unidades monetarias (no centavos). None si falta
    cualquiera de los dos insumos o el peso no es positivo — nunca se
    divide entre cero ni se asume un peso."""
    if price is None or net_weight_g is None or net_weight_g <= 0:
        return None
    result = (price / net_weight_g) * Decimal(100)
    return result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
