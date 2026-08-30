"""
Modelos pydantic compartidos por todos los adaptadores de plataforma.

Estos modelos son el "idioma común" entre core/<plataforma>.py y el
pipeline (Fase 5/6) — un adaptador nuevo (Shopify, custom) debe producir
exactamente estos tipos desde discover()/fetch()/parse(), sin que el
pipeline necesite saber qué plataforma los generó.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class RegionContext(BaseModel):
    """Contexto de región resuelto por resolve_region() para un CP dado."""

    model_config = ConfigDict(frozen=True)

    postal_code: str
    platform_data: dict[str, Any] = Field(default_factory=dict)
    """Datos crudos específicos de la plataforma (regionId, sellers
    disponibles, sales channel, etc. — ver core/vtex.py para el shape
    concreto de VTEX)."""


class SkuRef(BaseModel):
    """Referencia a un SKU descubierto por discover(), con su metadata de
    catálogo — TODAVÍA sin precio/stock reales (eso lo trae fetch())."""

    sku: str
    product_id: str
    name: str
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    ean: Optional[str] = None
    category_path: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    raw_specifications: dict[str, Any] = Field(default_factory=dict)
    """Specs crudas del retailer (p.ej. VTEX 'Contenido del empaque',
    'Presentación') — insumo para la normalización de gramaje."""
    raw_item: dict[str, Any] = Field(default_factory=dict)
    """El item crudo tal cual lo devolvió la plataforma (measurementUnit,
    unitMultiplier, etc.) — insumo adicional de normalización."""
    discovery_routes: list[str] = Field(default_factory=list)
    """Por cuál(es) ruta(s) de discover() se encontró este SKU —
    'categoria' | 'marca' | 'texto_libre'. Lo usa scope_filter.py: si vino
    de la categoría propia del retailer y no matchea ninguna exclusión
    dura, se confía en la categorización del retailer por default (ver
    Fase 3 — 602 productos de Chedraui solo se encontraban por esta ruta,
    sin keyword propio reconocible)."""


class RawPayload(BaseModel):
    """Resultado crudo de fetch(): metadata de catálogo (de discover) +
    precio/stock real por SKU (de la fuente de precio de la plataforma)."""

    sku_refs: list[SkuRef]
    price_data: dict[str, dict[str, Any]]
    """sku -> payload crudo de precio/stock (p.ej. un item de la respuesta
    de VTEX `simulation`). Puede faltar un sku si la fuente de precio no
    lo devolvió (needs_review en parse())."""


class Product(BaseModel):
    """Un producto normalizado, listo para persistir (products + el
    price_event más reciente)."""

    retailer_domain: str
    sku: str
    gtin: Optional[str] = None
    name: str
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    category_path: Optional[str] = None
    net_weight_g: Optional[Decimal] = None
    package_type: Optional[str] = None
    units_per_pack: int = 1
    needs_review: bool = False
    url: Optional[str] = None
    image_url: Optional[str] = None

    price_list: Optional[Decimal] = None
    price_sale: Optional[Decimal] = None
    price_per_100g: Optional[Decimal] = None
    currency: str = "MXN"
    in_stock: bool = False
    promo_label: Optional[str] = None
    seller: Optional[str] = None
    source_postal_code: Optional[str] = None
