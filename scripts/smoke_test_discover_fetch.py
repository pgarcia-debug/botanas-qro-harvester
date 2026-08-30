"""
Smoke test de Fase 5 — NO es parte del pipeline de producción.

Corre discover() + scope_filter + fetch() + parse() de verdad contra
Chedraui (red real) sobre una sola categoría chica ("Botanas a granel",
9 productos en Fase 3) y vuelca los Product resultantes a JSON, para
insertarlos vía el MCP de Supabase y probar idempotencia sin necesitar
DATABASE_URL en este entorno.
"""

import asyncio
import json
from decimal import Decimal

from core import scope_filter, vtex
from core.config import RetailerConfig


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(o)


async def main():
    config = RetailerConfig(
        name="Chedraui",
        domain="www.chedraui.com.mx",
        platform="VTEX",
        sales_channel="1",
        postal_code="76000",
        category_paths=["/1/111/11104/"],  # Botanas a granel — 9 productos en Fase 3
        brand_seed=[],
        generic_terms=[],
        overrides={"requires_browser_like_headers": True},
    )

    client = vtex.make_client(config)
    async with client:
        region = await vtex.resolve_region(client, config)
        print("region_id:", region.platform_data.get("region_id"))

        sku_refs = await vtex.discover(client, config, region)
        print(f"discover(): {len(sku_refs)} SKUs")

        in_scope = []
        for ref in sku_refs:
            decision = scope_filter.classify(ref.name, ref.discovery_routes)
            print(f"  [{'IN' if decision.include else 'OUT'}] {ref.name} — {decision.reason}")
            if decision.include:
                in_scope.append(ref)
        print(f"en alcance: {len(in_scope)}")

        raw = await vtex.fetch(client, config, region, in_scope)
        products = vtex.parse(raw, config)
        print(f"parse(): {len(products)} products")

        with open("smoke_test_products.json", "w", encoding="utf-8") as f:
            json.dump([p.model_dump() for p in products], f, ensure_ascii=False, indent=1, default=_default)


if __name__ == "__main__":
    asyncio.run(main())
