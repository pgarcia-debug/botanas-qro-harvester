"""
Fase 3 — Descubrimiento de la categoría botanas para Chedraui (exploratorio).

NO es el adaptador final (Fase 5) — es la herramienta de reconocimiento que
implementa las tres rutas complementarias que pide el brief y unifica por
SKU (aquí: productId de VTEX) para poder validar la delimitación de la
categoría antes de comprometernos a una implementación.

Usa httpx con headers de navegador + HTTP/2 para catálogo/búsqueda VTEX,
por la excepción aprobada en Fase 2/3 (ver CLAUDE.md) — el bot-shield de
VTEX bloquea el User-Agent identificable del proyecto en estos endpoints
públicos sin login.

Rutas:
  1. Árbol de categorías -> fq=C:<categoryId> sobre las ramas relevantes.
  2. Búsqueda por marca -> ft=<marca> sobre la semilla de marcas del brief.
  3. Full-text genérico -> ft=<término> sobre términos genéricos.

Salida: JSON con todos los productos únicos encontrados, taggeados por
ruta(s) de descubrimiento, más un resumen de conteos.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

BASE = "https://www.chedraui.com.mx"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Origin": BASE,
    "Referer": BASE + "/",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}

PAGE_SIZE = 50
MIN_INTERVAL = 1.0  # 1 req/s

# --- Rutas de descubrimiento ---

CATEGORY_IDS_PRIMARY = {
    # fq=C:<path> necesita la RUTA COMPLETA desde el departamento raíz
    # (verificado empíricamente contra categoriesIds de un producto
    # conocido: "/1/107/10710/" — no basta el id de hoja solo).
    "/1/107/10710/": "Botanas y frutos secos (despensa)",
    "/1/111/11104/": "Botanas (a granel)",
}
CATEGORY_IDS_FILTERED = {
    # Categoría ambigua: mezcla granos/legumbres de cocina con semillas
    # botaneras. Se consulta pero cada producto se filtra por keyword
    # antes de aceptarse (ver _looks_like_botana).
    "/1/107/10736/": "Granos y semillas (filtrado por producto)",
}

BRAND_SEED = [
    "Sabritas", "Doritos", "Cheetos", "Ruffles", "Rancheritos", "Fritos",
    "Tostitos", "Crujitos", "Sabritones", "Chips", "Barcel", "Takis",
    "Runners", "Golden Nuts", "Hot Nuts", "Big Mix", "Toreadas", "Bokados",
    "Encanto", "Totis", "Leo", "Pringles", "Mafer", "Nishikawa", "Karina",
    "Charras", "Act II", "Vualá",
]

GENERIC_TERMS = [
    "papas fritas", "frituras", "botana", "cacahuate", "palomitas",
    "chicharron", "semillas",
]

INCLUDE_KEYWORDS = [
    "papa", "papas", "frit", "tortilla", "chip", "churrito", "extrudid",
    "cacahuate", "cacahuat", "nuez", "nueces", "botanera", "semilla",
    "pepita", "chicharr", "palomita", "botana", "tostada", "takis",
    "cheeto", "dorito", "sabrit", "runner", "rancherit", "crujito",
]
EXCLUDE_KEYWORDS = [
    "chocolate", "dulce", "gomita", "paleta", "chicle", "caramelo",
    "galleta", "barra de cereal", "barrita", "cereal ", "arroz", "frijol",
    "lenteja", "avena", "harina", "azucar", "pasa ", "pasas ",
    "fruta deshidratada", "arandano", "higo", "ciruela pasa",
]


@dataclass
class Budget:
    last: float = 0.0

    async def wait(self):
        now = time.monotonic()
        elapsed = now - self.last
        if elapsed < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - elapsed)
        self.last = time.monotonic()


def _looks_like_botana(name: str) -> tuple[bool, str]:
    n = name.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in n:
            return False, f"excluido por keyword '{kw}'"
    for kw in INCLUDE_KEYWORDS:
        if kw in n:
            return True, f"incluido por keyword '{kw}'"
    return False, "sin keyword de inclusión reconocida"


def _build_query(params: dict) -> str:
    # IMPORTANTE: httpx.Client(params=...) codifica espacios como "+", y el
    # edge de VTEX/Chedraui rechaza "+" en la query string con
    # 400 "Bad Request! Scripts are not allowed!" (falso positivo de una
    # regla WAF ingenua) — pero acepta "%20" sin problema. Se construye la
    # query a mano con quote() para forzar %20.
    from urllib.parse import quote
    return "&".join(f"{k}={quote(str(v), safe='/:')}" for k, v in params.items())


async def _search_page(client: httpx.AsyncClient, budget: Budget, params: dict, _from: int, _to: int) -> list[dict]:
    await budget.wait()
    q = dict(params)
    q["_from"] = _from
    q["_to"] = _to
    url = f"{BASE}/api/catalog_system/pub/products/search?{_build_query(q)}"
    r = await client.get(url, timeout=20)
    if r.status_code == 206 or r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return []
    if r.status_code == 404:
        return []
    print(f"  [warn] status {r.status_code} for {q} -> {r.text[:120]}")
    return []


async def _search_all(client: httpx.AsyncClient, budget: Budget, params: dict, max_pages: int = 40) -> list[dict]:
    out = []
    seen_in_route = set()
    for page in range(max_pages):
        _from = page * PAGE_SIZE
        _to = _from + PAGE_SIZE - 1
        batch = await _search_page(client, budget, params, _from, _to)
        if not batch:
            break
        for p in batch:
            pid = p.get("productId")
            if pid and pid not in seen_in_route:
                seen_in_route.add(pid)
                out.append(p)
        if len(batch) < PAGE_SIZE:
            break
    return out


def _extract_min(p: dict) -> dict:
    item = (p.get("items") or [{}])[0]
    seller = (item.get("sellers") or [{}])[0]
    offer = seller.get("commertialOffer") or {}
    return {
        "productId": p.get("productId"),
        "name": p.get("productName"),
        "brand": p.get("brand"),
        "categoryPath (breadcrumb primer nivel de detalle)": p.get("categories", [None])[-1] if p.get("categories") else None,
        "ean": item.get("ean"),
        "price": offer.get("Price"),
    }


async def main():
    async with httpx.AsyncClient(headers=BROWSER_HEADERS, http2=True) as client:
        budget = Budget()
        routes: dict[str, dict[str, dict]] = {"categoria": {}, "marca": {}, "texto_libre": {}}

        # --- Ruta 1: árbol de categorías ---
        print("== Ruta 1: categorías ==")
        for cat_path, label in CATEGORY_IDS_PRIMARY.items():
            products = await _search_all(client, budget, {"fq": f"C:{cat_path}"})
            print(f"  cat {cat_path} ({label}): {len(products)} productos")
            for p in products:
                routes["categoria"][p["productId"]] = p

        for cat_path, label in CATEGORY_IDS_FILTERED.items():
            products = await _search_all(client, budget, {"fq": f"C:{cat_path}"})
            accepted = 0
            for p in products:
                ok, reason = _looks_like_botana(p.get("productName", ""))
                if ok:
                    routes["categoria"][p["productId"]] = p
                    accepted += 1
            print(f"  cat {cat_path} ({label}): {len(products)} productos, {accepted} aceptados tras filtro de keyword")

        # --- Ruta 2: búsqueda por marca ---
        print("== Ruta 2: marca ==")
        for brand in BRAND_SEED:
            products = await _search_all(client, budget, {"ft": brand}, max_pages=6)
            hits = 0
            for p in products:
                ok, reason = _looks_like_botana(p.get("productName", ""))
                if ok:
                    routes["marca"][p["productId"]] = p
                    hits += 1
            if products:
                print(f"  marca '{brand}': {len(products)} resultados, {hits} aceptados")

        # --- Ruta 3: full-text genérico ---
        print("== Ruta 3: texto libre ==")
        for term in GENERIC_TERMS:
            products = await _search_all(client, budget, {"ft": term}, max_pages=10)
            hits = 0
            for p in products:
                ok, reason = _looks_like_botana(p.get("productName", ""))
                if ok:
                    routes["texto_libre"][p["productId"]] = p
                    hits += 1
            print(f"  término '{term}': {len(products)} resultados, {hits} aceptados")

        # --- Unificación ---
        all_ids = set()
        for r in routes.values():
            all_ids |= set(r.keys())

        by_id: dict[str, dict] = {}
        for r in routes.values():
            for pid, p in r.items():
                by_id[pid] = p

        route_membership = {}
        for pid in all_ids:
            member = [name for name, r in routes.items() if pid in r]
            route_membership[pid] = member

        print("\n== Resumen ==")
        for name, r in routes.items():
            print(f"  {name}: {len(r)} SKUs únicos")
        print(f"  UNIÓN total: {len(all_ids)} SKUs únicos")
        only_one_route = sum(1 for m in route_membership.values() if len(m) == 1)
        all_three = sum(1 for m in route_membership.values() if len(m) == 3)
        print(f"  encontrados en 1 sola ruta: {only_one_route}")
        print(f"  encontrados en las 3 rutas: {all_three}")

        out = {
            "counts": {name: len(r) for name, r in routes.items()},
            "union_total": len(all_ids),
            "products": [
                {**_extract_min(by_id[pid]), "routes": route_membership[pid]}
                for pid in all_ids
            ],
        }
        with open("fase3_chedraui_raw.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\nGuardado en fase3_chedraui_raw.json")


if __name__ == "__main__":
    asyncio.run(main())
