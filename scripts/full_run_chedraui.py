"""
Corrida real completa de Chedraui (todas las categorías de Fase 3) contra
la red real, volcada a JSON — para insertar vía el MCP de Supabase (no
usa core/db.py con asyncpg porque no hay DATABASE_URL en este entorno,
ver limitación documentada en docs/fase5-adaptador-vtex.md).

NO es parte del pipeline de producción — es una corrida puntual para
validar con datos reales a escala completa.
"""

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path

from core import scope_filter, vtex
from core.config import load_retailer_config

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = Path(os.environ.get("FULL_RUN_OUT", REPO_ROOT / "full_run_products.json"))


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(o)


async def main():
    config = load_retailer_config(REPO_ROOT / "retailers" / "chedraui.yaml")

    client = vtex.make_client(config)
    stats = vtex.RequestStats()
    async with client:
        region = await vtex.resolve_region(client, config, stats=stats)
        print("region_id:", region.platform_data.get("region_id"))

        sku_refs = await vtex.discover(client, config, region, stats=stats)
        print(f"discover(): {len(sku_refs)} SKUs")

        in_scope = []
        excluded = 0
        for ref in sku_refs:
            decision = scope_filter.classify(ref.name, ref.discovery_routes)
            if decision.include:
                in_scope.append(ref)
            else:
                excluded += 1
        print(f"en alcance: {len(in_scope)} (excluidos: {excluded})")

        raw = await vtex.fetch(client, config, region, in_scope, stats=stats)
        products = vtex.parse(raw, config)
        print(f"parse(): {len(products)} products")
        print(f"blocked_rate: {stats.blocked_rate:.1%} ({stats.status_403} x403, {stats.status_429} x429 de {stats.total_attempts} intentos)")

        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump([p.model_dump() for p in products], f, ensure_ascii=False, indent=1, default=_default)
        print(f"guardado en {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
