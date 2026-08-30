"""
Adaptador de plataforma VTEX.

Implementa la interfaz de 4 funciones de CLAUDE.md. Firma real (afinada en
Fase 5 respecto al esbozo original — cada función necesita el config del
retailer para saber a qué dominio pegarle y con qué parámetros, ya que eso
varía por retailer aunque la plataforma sea la misma VTEX):

    resolve_region(client, config, stats=None)          -> RegionContext
    discover(client, config, region, stats=None)         -> list[SkuRef]
    fetch(client, config, region, sku_refs, stats=None)   -> RawPayload
    parse(raw, config)                                     -> list[Product]

`stats` (RequestStats, Fase 6) es opcional y compartido entre las tres
llamadas de I/O de un mismo run — cuenta tasa de 403/429 para la guarda de
calidad correspondiente.

`parse()` es la única función sin I/O — puro cómputo sobre datos ya
descargados, por eso es la que se prueba con fixtures reales sin red.

Hallazgos de Fase 2/3 que este módulo encapsula (no repetir en otro lado):
  - La API legacy de catálogo (`/api/catalog_system/pub/products/search`)
    NO respeta el contexto de región — sirve para discover() (metadata),
    NUNCA como fuente de precio.
  - El precio real por tienda sale de
    `/api/checkout/pub/orderForms/simulation`, es stateless (basta
    `postalCode` en el body) y soporta batch.
  - `fq=C:<path>` necesita la ruta completa desde el departamento raíz
    (p.ej. "/1/107/10710/"), no el id de hoja solo.
  - Espacios en query params deben ir como %20, no "+" (el edge de VTEX
    rechaza "+" con 400 "Bad Request! Scripts are not allowed!").
  - El backend de checkout Y el de catálogo bloquean el User-Agent
    identificable del proyecto con 429 "rate-limit-reason: bot" — se
    resuelve con HTTP/2 + headers de navegador en todo el tráfico VTEX
    (excepción aprobada, ver CLAUDE.md).
  - El campo más confiable de gramaje es la spec "Contenido del empaque"
    (p.ej. "1 pieza de 160g"), no el nombre del producto — ver
    core/normalize.py.
"""

from __future__ import annotations

import asyncio
import random
import time
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import quote

import httpx

from core.config import RetailerConfig
from core.models import Product, RawPayload, RegionContext, SkuRef
from core.normalize import calc_price_per_100g, resolve_weight

PAGE_SIZE = 50
MAX_PAGES = 60  # cubre hasta 3000 resultados — la categoría más grande vista en Fase 3 fue 1370
SIMULATION_BATCH_SIZE = 20
MAX_RETRIES = 3

BROWSER_HEADERS_TEMPLATE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}
IDENTIFIABLE_USER_AGENT = "BotanasQroHarvester/0.1 (+contacto:paregava@gmail.com)"


def make_client(config: RetailerConfig) -> httpx.AsyncClient:
    """Cliente httpx configurado para este retailer. VTEX requiere
    HTTP/2 + headers de navegador (excepción aprobada, ver CLAUDE.md);
    otras plataformas usarían el UA identificable por default."""
    base = f"https://{config.domain}"
    if config.overrides.get("requires_browser_like_headers"):
        headers = {**BROWSER_HEADERS_TEMPLATE, "Origin": base, "Referer": base + "/"}
        return httpx.AsyncClient(headers=headers, http2=True, timeout=config.timeout_s)
    headers = {"User-Agent": IDENTIFIABLE_USER_AGENT, "Accept-Language": "es-MX,es;q=0.9"}
    return httpx.AsyncClient(headers=headers, timeout=config.timeout_s)


class _RateBudget:
    """1 req/s (configurable) por dominio, con backoff exponencial+jitter
    en reintentos — CLAUDE.md."""

    def __init__(self, rps: float):
        self._min_interval = 1.0 / rps if rps > 0 else 1.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last = time.monotonic()


class RequestStats:
    """Cuenta cada intento de request y cuántos de esos fueron 403/429 —
    alimenta la guarda de calidad "tasa de 403/429 > 10%" de Fase 6. Se
    cuenta CADA intento (incluidos los que el retry interno reintenta),
    no solo el resultado final, porque lo que importa para la guarda es
    cuánto está empujando el servidor hacia atrás, no si al final se
    logró colar la request."""

    def __init__(self) -> None:
        self.total_attempts = 0
        self.status_403 = 0
        self.status_429 = 0

    def record(self, status_code: Optional[int]) -> None:
        self.total_attempts += 1
        if status_code == 403:
            self.status_403 += 1
        elif status_code == 429:
            self.status_429 += 1

    @property
    def blocked_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return (self.status_403 + self.status_429) / self.total_attempts


async def _get(
    client: httpx.AsyncClient, budget: _RateBudget, url: str, stats: Optional[RequestStats] = None
) -> Optional[httpx.Response]:
    for attempt in range(MAX_RETRIES):
        await budget.wait()
        try:
            resp = await client.get(url)
        except (httpx.TimeoutException, httpx.TransportError):
            if stats:
                stats.record(None)
            await asyncio.sleep(2**attempt + random.uniform(0, 1))
            continue
        if stats:
            stats.record(resp.status_code)
        if resp.status_code in (429, 503):
            await asyncio.sleep(2**attempt + random.uniform(0, 1))
            continue
        return resp
    return None


async def _post(
    client: httpx.AsyncClient, budget: _RateBudget, url: str, json_body: dict, stats: Optional[RequestStats] = None
) -> Optional[httpx.Response]:
    for attempt in range(MAX_RETRIES):
        await budget.wait()
        try:
            resp = await client.post(url, json=json_body)
        except (httpx.TimeoutException, httpx.TransportError):
            if stats:
                stats.record(None)
            await asyncio.sleep(2**attempt + random.uniform(0, 1))
            continue
        if stats:
            stats.record(resp.status_code)
        if resp.status_code in (429, 503):
            await asyncio.sleep(2**attempt + random.uniform(0, 1))
            continue
        return resp
    return None


def _build_search_url(base: str, params: dict[str, Any]) -> str:
    # httpx.Client(params=...) codifica espacios como "+", que el edge de
    # VTEX rechaza con 400 — se fuerza %20 a mano. Ver docstring del módulo.
    qs = "&".join(f"{k}={quote(str(v), safe='/:')}" for k, v in params.items())
    return f"{base}/api/catalog_system/pub/products/search?{qs}"


# =====================================================================
# resolve_region
# =====================================================================

async def resolve_region(
    client: httpx.AsyncClient, config: RetailerConfig, stats: Optional[RequestStats] = None
) -> RegionContext:
    budget = _RateBudget(config.rate_limit_rps)
    base = f"https://{config.domain}"
    url = f"{base}/api/checkout/pub/regions?country=MEX&postalCode={config.postal_code}&sc={config.sales_channel}"
    resp = await _get(client, budget, url, stats)
    if resp is None or resp.status_code != 200:
        raise RuntimeError(
            f"No se pudo resolver la región para {config.name} (CP {config.postal_code}): "
            f"status={resp.status_code if resp else 'sin respuesta'}"
        )
    regions = resp.json()
    if not regions:
        raise RuntimeError(f"VTEX no devolvió ninguna región para CP {config.postal_code} en {config.name}")
    # Puede haber más de una región candidata; se toma la primera — ver
    # docs/fase2-regionalizacion-chedraui.md sobre por qué esto es
    # suficiente (simulation resuelve el seller correcto igual, es
    # stateless por postalCode).
    region = regions[0]
    return RegionContext(
        postal_code=config.postal_code,
        platform_data={
            "region_id": region.get("id"),
            "sellers": region.get("sellers", []),
            "sales_channel": config.sales_channel,
        },
    )


# =====================================================================
# discover
# =====================================================================

async def _search_all(
    client: httpx.AsyncClient,
    budget: _RateBudget,
    base: str,
    params: dict[str, Any],
    max_pages: int = MAX_PAGES,
    stats: Optional[RequestStats] = None,
) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for page in range(max_pages):
        _from = page * PAGE_SIZE
        _to = _from + PAGE_SIZE - 1
        url = _build_search_url(base, {**params, "_from": _from, "_to": _to})
        resp = await _get(client, budget, url, stats)
        if resp is None or resp.status_code not in (200, 206):
            break
        try:
            batch = resp.json()
        except ValueError:
            break
        if not batch:
            break
        for p in batch:
            pid = p.get("productId")
            if pid and pid not in seen:
                seen.add(pid)
                out.append(p)
        if len(batch) < PAGE_SIZE:
            break
    return out


def _product_to_skuref(p: dict) -> Optional[SkuRef]:
    items = p.get("items") or []
    if not items:
        return None
    item = items[0]
    categories = p.get("categories") or []
    images = item.get("images") or []
    return SkuRef(
        sku=item.get("itemId") or p.get("productId"),
        product_id=p.get("productId", ""),
        name=p.get("productName", ""),
        brand=p.get("brand") or None,
        ean=item.get("ean") or None,
        category_path=categories[0] if categories else None,
        url=p.get("link"),
        image_url=images[0].get("imageUrl") if images else None,
        raw_specifications={
            "Contenido del empaque": p.get("Contenido del empaque"),
            "Presentación": p.get("Presentación"),
        },
        raw_item=item,
    )


async def discover(
    client: httpx.AsyncClient,
    config: RetailerConfig,
    region: RegionContext,
    stats: Optional[RequestStats] = None,
) -> list[SkuRef]:
    """Las 3 rutas complementarias de Fase 3: árbol de categorías,
    búsqueda por marca, full-text genérico. Unifica por productId,
    registrando por cuál(es) ruta(s) se encontró cada uno (lo usa
    scope_filter.py). NO filtra por relevancia a "botanas" — eso es
    scope_filter.py, que corre después (es lógica de categoría del
    proyecto, no de VTEX)."""
    budget = _RateBudget(config.rate_limit_rps)
    base = f"https://{config.domain}"
    by_product_id: dict[str, dict] = {}
    routes_by_product_id: dict[str, set[str]] = {}

    def _record(products: list[dict], route: str) -> None:
        for p in products:
            pid = p["productId"]
            by_product_id.setdefault(pid, p)
            routes_by_product_id.setdefault(pid, set()).add(route)

    for cat_path in config.category_paths:
        products = await _search_all(client, budget, base, {"fq": f"C:{cat_path}"}, stats=stats)
        _record(products, "categoria")

    for brand in config.brand_seed:
        products = await _search_all(client, budget, base, {"ft": brand}, max_pages=10, stats=stats)
        _record(products, "marca")

    for term in config.generic_terms:
        products = await _search_all(client, budget, base, {"ft": term}, max_pages=15, stats=stats)
        _record(products, "texto_libre")

    sku_refs = []
    for pid, p in by_product_id.items():
        ref = _product_to_skuref(p)
        if ref is not None:
            ref.discovery_routes = sorted(routes_by_product_id.get(pid, set()))
            sku_refs.append(ref)
    return sku_refs


# =====================================================================
# fetch
# =====================================================================

async def fetch(
    client: httpx.AsyncClient,
    config: RetailerConfig,
    region: RegionContext,
    sku_refs: list[SkuRef],
    stats: Optional[RequestStats] = None,
) -> RawPayload:
    """Precio/stock real vía checkout simulation, batched. Stateless: el
    postalCode va en cada request, no depende de cookies de sesión (ver
    docs/fase2-regionalizacion-chedraui.md)."""
    budget = _RateBudget(config.rate_limit_rps)
    base = f"https://{config.domain}"
    url = f"{base}/api/checkout/pub/orderForms/simulation"

    price_data: dict[str, dict[str, Any]] = {}
    for i in range(0, len(sku_refs), SIMULATION_BATCH_SIZE):
        batch = sku_refs[i : i + SIMULATION_BATCH_SIZE]
        body = {
            "items": [{"id": ref.sku, "quantity": 1, "seller": "1"} for ref in batch],
            "postalCode": config.postal_code,
            "country": "MEX",
        }
        resp = await _post(client, budget, url, body, stats)
        if resp is None or resp.status_code != 200:
            continue  # el pipeline cuenta estos como items_err vía la ausencia en price_data
        try:
            result = resp.json()
        except ValueError:
            continue
        for item in result.get("items", []):
            price_data[item["id"]] = item

    return RawPayload(sku_refs=sku_refs, price_data=price_data)


# =====================================================================
# parse — pura, sin I/O. Se prueba con fixtures reales sin red.
# =====================================================================

def _cents_to_decimal(cents: Optional[int]) -> Optional[Decimal]:
    if cents is None:
        return None
    return Decimal(cents) / Decimal(100)


def _extract_promo_label(item: dict) -> Optional[str]:
    tags = item.get("priceTags") or []
    labels = [t.get("name") for t in tags if isinstance(t, dict) and t.get("name")]
    return "; ".join(labels) if labels else None


def parse(raw: RawPayload, config: RetailerConfig) -> list[Product]:
    products: list[Product] = []
    for ref in raw.sku_refs:
        price_item = raw.price_data.get(ref.sku)
        if price_item is None:
            # No hay dato de precio para este SKU (falla puntual de la API,
            # SKU discontinuado, etc.) — el pipeline lo cuenta como error,
            # no se inventa un Product a medias.
            continue

        specs = ref.raw_specifications
        package_content = specs.get("Contenido del empaque")
        package_content_str = package_content[0] if package_content else None
        presentacion = specs.get("Presentación")
        package_type = presentacion[0] if presentacion else None

        weight = resolve_weight(
            name=ref.name,
            package_content_spec=package_content_str,
            measurement_unit=ref.raw_item.get("measurementUnit"),
            unit_multiplier=ref.raw_item.get("unitMultiplier"),
        )

        price_list = _cents_to_decimal(price_item.get("listPrice"))
        price_sale = _cents_to_decimal(price_item.get("price"))
        price_for_100g = price_sale if price_sale is not None else price_list
        price_per_100g = (
            None if weight.needs_review else calc_price_per_100g(price_for_100g, weight.net_weight_g)
        )

        seller_chain = price_item.get("sellerChain") or []
        seller = seller_chain[-1] if seller_chain else None

        products.append(
            Product(
                retailer_domain=config.domain,
                sku=ref.sku,
                gtin=ref.ean,
                name=ref.name,
                brand=ref.brand,
                manufacturer=None,  # VTEX no expone fabricante de forma confiable en este catálogo
                category_path=ref.category_path,
                net_weight_g=weight.net_weight_g,
                package_type=package_type,
                units_per_pack=weight.units_per_pack,
                needs_review=weight.needs_review,
                url=ref.url,
                image_url=ref.image_url,
                price_list=price_list,
                price_sale=price_sale,
                price_per_100g=price_per_100g,
                currency="MXN",
                in_stock=price_item.get("availability") == "available",
                promo_label=_extract_promo_label(price_item),
                seller=seller,
                source_postal_code=config.postal_code,
            )
        )
    return products
