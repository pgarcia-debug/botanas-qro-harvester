"""
Fase 1 — Fingerprint de plataforma por dominio.

Detecta la plataforma e-commerce de un dominio de retail probando señales
en orden de costo (barato -> caro):

  1. VTEX Search API   (GET /api/catalog_system/pub/products/search)
  2. VTEX category tree (GET /api/catalog_system/pub/category/tree/3) — confirma #1
  3. Shopify            (/products.json, header X-Shopify-*)
  4. Señales embebidas en HTML (__NEXT_DATA__, __INITIAL_STATE__, JSON-LD, sitemap.xml)
  5. WAF hostil          (headers/cookies de Akamai, Cloudflare, PerimeterX, DataDome)

No asume nada: cada señal se verifica con una request real. robots.txt se
respeta y se reporta si bloquea las rutas que necesitaríamos.

Uso:
    python tools/fingerprint.py                      # corre sobre la lista default
    python tools/fingerprint.py dominio1.com dominio2.com
    python tools/fingerprint.py --json out.json       # además del markdown, guarda JSON crudo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

USER_AGENT = "BotanasQroHarvester/0.1 (+contacto:paregava@gmail.com; investigacion de precios, uso educativo/personal)"
TIMEOUT = 20.0
MAX_RETRIES = 3
PER_DOMAIN_MIN_INTERVAL = 1.0  # 1 req/s por dominio

WAF_HEADER_SIGNATURES = {
    "cloudflare": [
        ("server", "cloudflare"),
        ("cf-ray", None),
        ("cf-mitigated", None),
    ],
    "akamai": [
        ("server", "akamaighost"),
        ("x-akamai-transformed", None),
        ("akamai-grn", None),
        ("x-akamai-request-id", None),
        ("x-edgeconnect-midmile-rtt", None),
        ("x-edgeconnect-origin-mex-latency", None),
    ],
    "perimeterx": [
        ("x-px", None),
        ("x-px-block-reason", None),
    ],
    "datadome": [
        ("x-datadome", None),
        ("x-dd-b", None),
    ],
    "incapsula": [
        ("x-iinfo", None),
        ("x-cdn", "incapsula"),
    ],
}
WAF_COOKIE_SIGNATURES = {
    "perimeterx": ["_px", "_pxhd", "_pxvid", "_px3", "_pxff_cc"],
    "datadome": ["datadome"],
    "cloudflare": ["__cf_bm", "cf_clearance"],
    "akamai": ["_abck", "ak_bmsc", "bm_sv"],
}


@dataclass
class DomainBudget:
    """Enforces 1 req/s per domain across all probes for that domain."""

    last_request_ts: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def wait_turn(self) -> None:
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_request_ts
            if elapsed < PER_DOMAIN_MIN_INTERVAL:
                await asyncio.sleep(PER_DOMAIN_MIN_INTERVAL - elapsed)
            self.last_request_ts = time.monotonic()


@dataclass
class ProbeResult:
    url: str
    status: Optional[int] = None
    error: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)
    body_snippet: str = ""
    json_body: Optional[Any] = None
    elapsed_ms: Optional[int] = None


@dataclass
class DomainReport:
    domain: str
    robots_txt: Optional[str] = None
    robots_blocks_api: Optional[bool] = None
    probes: dict[str, ProbeResult] = field(default_factory=dict)
    waf_hits: list[str] = field(default_factory=list)
    platform: str = "DESCONOCIDA"
    useful_endpoint: str = ""
    requires_region: str = ""
    viability: str = "ROJO"
    notes: list[str] = field(default_factory=list)
    error: Optional[str] = None


async def _request_with_retry(
    client: httpx.AsyncClient,
    budget: DomainBudget,
    method: str,
    url: str,
    **kwargs,
) -> ProbeResult:
    kwargs.setdefault("follow_redirects", True)
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        await budget.wait_turn()
        start = time.monotonic()
        try:
            resp = await client.request(method, url, timeout=TIMEOUT, **kwargs)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            body_text = ""
            json_body = None
            try:
                body_text = resp.text[:4000]
            except Exception:
                body_text = ""
            ctype = resp.headers.get("content-type", "")
            if "json" in ctype:
                try:
                    json_body = resp.json()
                except Exception:
                    json_body = None
            result = ProbeResult(
                url=str(resp.url),
                status=resp.status_code,
                headers={k.lower(): v for k, v in resp.headers.items()},
                cookies=list(resp.cookies.keys()),
                body_snippet=body_text,
                json_body=json_body,
                elapsed_ms=elapsed_ms,
            )
            if resp.status_code in (429, 503):
                last_exc = RuntimeError(f"HTTP {resp.status_code}")
                await _backoff_sleep(attempt)
                continue
            return result
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # Nota: ConnectError (incluye fallas de resolución DNS) se trata
            # igual que un timeout, con reintento+backoff. En Windows, con
            # muchos dominios resolviéndose en paralelo, getaddrinfo puede
            # fallar transitoriamente por contención del resolver — no
            # significa necesariamente que el host esté caído o rechace
            # conexión de verdad. Fallar rápido aquí producía falsos ROJO.
            last_exc = exc
            await _backoff_sleep(attempt)
            continue
    if isinstance(last_exc, httpx.ConnectError) and "CERTIFICATE_VERIFY_FAILED" in str(last_exc):
        # Diagnóstico único, SOLO para este fingerprint de reconocimiento:
        # reintenta sin validar TLS para poder seguir inspeccionando la
        # plataforma, pero lo marca fuerte en el resultado. Esto NUNCA debe
        # replicarse en el harvester de producción (Fase 5+) sin decisión
        # explícita — un cert roto ahí se investiga, no se ignora.
        try:
            await budget.wait_turn()
            resp = await client.request(method, url, timeout=TIMEOUT, **{**kwargs, "verify": False})
            body_text = resp.text[:4000] if True else ""
            json_body = None
            if "json" in resp.headers.get("content-type", ""):
                try:
                    json_body = resp.json()
                except Exception:
                    json_body = None
            return ProbeResult(
                url=str(resp.url),
                status=resp.status_code,
                headers={k.lower(): v for k, v in resp.headers.items()},
                cookies=list(resp.cookies.keys()),
                body_snippet=body_text,
                json_body=json_body,
                error=f"TLS_VERIFY_FAILED (respondió igual sin validar cert — investigar cadena de certificados del servidor): {last_exc}",
            )
        except Exception:
            pass
    return ProbeResult(url=url, error=str(last_exc) if last_exc else "unknown error")


async def _resolve_effective_host(client: httpx.AsyncClient, budget: DomainBudget, domain: str) -> tuple[str, Optional[str]]:
    """Algunos dominios rechazan conexión en el apex y solo responden en www.
    (p.ej. chedraui.com.mx). Probamos apex primero; si falla por CUALQUIER
    error de red (no solo "connection refused" — DNS transitorio, TLS, etc.
    caen todos en la misma categoría aquí), caemos a www.<domain>. Devuelve
    (host_efectivo, nota|None)."""
    probe = await _request_with_retry(client, budget, "GET", f"https://{domain}/")
    if probe.status is None and not domain.startswith("www."):
        www_host = f"www.{domain}"
        probe2 = await _request_with_retry(client, budget, "GET", f"https://{www_host}/")
        if not probe2.error:
            return www_host, f"apex {domain} falló ({probe.error}); se usó {www_host}"
    return domain, None


async def _backoff_sleep(attempt: int) -> None:
    base = 2**attempt
    jitter = random.uniform(0, 1)
    await asyncio.sleep(base + jitter)


def _detect_waf(probe: ProbeResult) -> list[str]:
    hits = []
    for waf_name, header_sigs in WAF_HEADER_SIGNATURES.items():
        for header_name, expected_value in header_sigs:
            actual = probe.headers.get(header_name)
            if actual is None:
                continue
            if expected_value is None or expected_value in actual.lower():
                hits.append(waf_name)
                break
    for waf_name, cookie_names in WAF_COOKIE_SIGNATURES.items():
        for cookie_name in cookie_names:
            if any(cookie_name in c for c in probe.cookies):
                if waf_name not in hits:
                    hits.append(waf_name)
    return hits


async def _check_robots(client: httpx.AsyncClient, budget: DomainBudget, domain: str) -> tuple[Optional[str], Optional[bool]]:
    url = f"https://{domain}/robots.txt"
    probe = await _request_with_retry(client, budget, "GET", url)
    if probe.error or probe.status != 200:
        return None, None
    text = probe.body_snippet
    rp = robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    blocks_api = not rp.can_fetch(USER_AGENT, f"https://{domain}/api/catalog_system/pub/products/search")
    return text[:2000], blocks_api


async def _probe_vtex_search(client, budget, domain) -> ProbeResult:
    url = f"https://{domain}/api/catalog_system/pub/products/search?_from=0&_to=1"
    return await _request_with_retry(client, budget, "GET", url)


async def _probe_vtex_tree(client, budget, domain) -> ProbeResult:
    url = f"https://{domain}/api/catalog_system/pub/category/tree/3"
    return await _request_with_retry(client, budget, "GET", url)


async def _probe_shopify_products_json(client, budget, domain) -> ProbeResult:
    url = f"https://{domain}/products.json?limit=1"
    return await _request_with_retry(client, budget, "GET", url)


async def _probe_homepage(client, budget, domain) -> ProbeResult:
    url = f"https://{domain}/"
    return await _request_with_retry(client, budget, "GET", url, follow_redirects=True)


async def _probe_sitemap(client, budget, domain) -> ProbeResult:
    url = f"https://{domain}/sitemap.xml"
    return await _request_with_retry(client, budget, "GET", url)


def _looks_like_vtex_product_array(json_body: Any) -> bool:
    if isinstance(json_body, list):
        if len(json_body) == 0:
            return True  # empty but valid VTEX array response (category with no seed match)
        first = json_body[0]
        return isinstance(first, dict) and ("productId" in first or "items" in first or "productName" in first)
    return False


def _looks_like_vtex_tree(json_body: Any) -> bool:
    if isinstance(json_body, list) and len(json_body) > 0:
        first = json_body[0]
        return isinstance(first, dict) and ("id" in first and "name" in first and "children" in first)
    return False


def _homepage_signals(body: str) -> list[str]:
    signals = []
    if "__NEXT_DATA__" in body:
        signals.append("__NEXT_DATA__ (Next.js)")
    if "__INITIAL_STATE__" in body:
        signals.append("__INITIAL_STATE__")
    if re.search(r'"@type"\s*:\s*"Product"', body) or "application/ld+json" in body:
        signals.append("JSON-LD")
    if "vtex" in body.lower():
        signals.append("mención literal 'vtex' en HTML")
    if "cdn.shopify.com" in body.lower() or "Shopify.theme" in body:
        signals.append("cdn.shopify.com / Shopify.theme")
    if "window.__PRELOADED_STATE__" in body:
        signals.append("__PRELOADED_STATE__")
    if "aktiosdigitalservices.com" in body.lower():
        signals.append("CDN aktiosdigitalservices.com (plataforma 'Aktios' — vendor de e-commerce para retail MX)")
    if "/spartacus/" in body:
        signals.append("Spartacus/SAP Commerce (Hybris)")
    elif "data-critters-container" in body:
        # "critters" es una lib genérica de inlining de CSS para Angular
        # Universal SSR — la usan muchas apps Angular, no solo SAP Commerce.
        # Señal débil: solo dice "Angular SSR", no identifica la plataforma.
        signals.append("Angular Universal SSR (plataforma custom, sin identificar aún)")
    return signals


async def fingerprint_domain(client: httpx.AsyncClient, domain: str) -> DomainReport:
    report = DomainReport(domain=domain)
    budget = DomainBudget()

    try:
        effective_host, host_note = await _resolve_effective_host(client, budget, domain)
        if host_note:
            report.notes.append(host_note)

        robots_text, blocks_api = await _check_robots(client, budget, effective_host)
        report.robots_txt = robots_text
        report.robots_blocks_api = blocks_api

        # --- Señal 1: VTEX search API ---
        vtex_search = await _probe_vtex_search(client, budget, effective_host)
        report.probes["vtex_search"] = vtex_search
        report.waf_hits += [w for w in _detect_waf(vtex_search) if w not in report.waf_hits]

        is_vtex = False
        # VTEX responde 200 (o 206 Partial Content — usa Content-Range para paginación)
        # cuando el endpoint de búsqueda existe.
        if vtex_search.status in (200, 206) and _looks_like_vtex_product_array(vtex_search.json_body):
            is_vtex = True
        elif vtex_search.headers and "vtex" in json.dumps(vtex_search.headers).lower():
            is_vtex = True

        # --- Señal 2: VTEX category tree (confirmación) ---
        if is_vtex or vtex_search.status in (200, 206):
            vtex_tree = await _probe_vtex_tree(client, budget, effective_host)
            report.probes["vtex_tree"] = vtex_tree
            report.waf_hits += [w for w in _detect_waf(vtex_tree) if w not in report.waf_hits]
            if vtex_tree.status == 200 and _looks_like_vtex_tree(vtex_tree.json_body):
                is_vtex = True

        if is_vtex:
            report.platform = "VTEX"
            report.useful_endpoint = "/api/catalog_system/pub/products/search (+ category/tree/3)"

        # --- Señal 3: Shopify ---
        if not is_vtex:
            shopify_probe = await _probe_shopify_products_json(client, budget, effective_host)
            report.probes["shopify_products_json"] = shopify_probe
            report.waf_hits += [w for w in _detect_waf(shopify_probe) if w not in report.waf_hits]
            is_shopify = False
            if shopify_probe.status == 200 and isinstance(shopify_probe.json_body, dict) and "products" in shopify_probe.json_body:
                is_shopify = True
            header_blob = json.dumps(shopify_probe.headers).lower()
            if "x-shopid" in header_blob or "x-shopify" in header_blob or "shopify" in shopify_probe.headers.get("server", "").lower():
                is_shopify = True
            if is_shopify:
                report.platform = "SHOPIFY"
                report.useful_endpoint = "/products.json"

        # --- Señal 4: homepage embebida (siempre la corremos: da señales de WAF y confirma/descarta) ---
        homepage = await _probe_homepage(client, budget, effective_host)
        report.probes["homepage"] = homepage
        report.waf_hits += [w for w in _detect_waf(homepage) if w not in report.waf_hits]

        if report.platform == "DESCONOCIDA" and homepage.body_snippet:
            signals = _homepage_signals(homepage.body_snippet)
            if signals:
                report.notes.append("Señales HTML: " + "; ".join(signals))
                if any("vtex" in s.lower() for s in signals):
                    report.platform = "VTEX (por señal HTML, no confirmado por API)"
                elif any("shopify" in s.lower() for s in signals):
                    report.platform = "SHOPIFY (por señal HTML, no confirmado por API)"
                elif any("Spartacus" in s for s in signals):
                    report.platform = "CUSTOM (SAP Commerce / Spartacus)"
                elif any("Aktios" in s for s in signals):
                    report.platform = "CUSTOM (vendor Aktios)"
                elif any("Next.js" in s for s in signals) or any("__INITIAL_STATE__" in s or "__PRELOADED_STATE__" in s for s in signals):
                    report.platform = "CUSTOM (SSR con estado embebido)"
                elif any("Angular Universal SSR" in s for s in signals):
                    report.platform = "CUSTOM (Angular Universal SSR, vendor sin identificar)"

        # sitemap como señal adicional barata de estructura
        sitemap = await _probe_sitemap(client, budget, effective_host)
        report.probes["sitemap"] = sitemap
        report.waf_hits += [w for w in _detect_waf(sitemap) if w not in report.waf_hits]

        # --- Señal 5: si hubo hits de WAF fuerte y no se pudo confirmar plataforma con datos limpios ---
        if report.waf_hits and report.platform == "DESCONOCIDA":
            report.platform = f"HOSTIL ({', '.join(report.waf_hits)})"

        # veredicto de viabilidad
        report.viability, viability_notes = _assess_viability(report)
        report.notes += viability_notes

    except Exception as exc:  # noqa: BLE001 — reporte defensivo, no debe tumbar el fingerprint completo
        report.error = f"{type(exc).__name__}: {exc}"
        report.viability = "ROJO"

    return report


def _assess_viability(report: DomainReport) -> tuple[str, list[str]]:
    notes = []
    if report.robots_blocks_api:
        notes.append("robots.txt bloquea la ruta /api que necesitaríamos.")

    strong_waf = {"perimeterx", "datadome"}
    hit_strong_waf = strong_waf.intersection(report.waf_hits)

    if report.platform == "VTEX":
        if hit_strong_waf:
            return "AMARILLO", notes + [f"VTEX confirmado pero con WAF fuerte al frente: {sorted(hit_strong_waf)}"]
        return "VERDE", notes + ["VTEX confirmado por API. Requiere resolver región (Fase 2)."]

    if report.platform == "SHOPIFY":
        if hit_strong_waf:
            return "AMARILLO", notes + [f"Shopify confirmado pero con WAF fuerte al frente: {sorted(hit_strong_waf)}"]
        return "VERDE", notes + ["Shopify confirmado vía /products.json."]

    if report.platform.startswith("CUSTOM"):
        return "AMARILLO", notes + ["Plataforma custom con estado embebido en HTML — viable sin navegador pero requiere parser a medida."]

    if report.platform.startswith("VTEX (por señal") or report.platform.startswith("SHOPIFY (por señal"):
        return "AMARILLO", notes + ["Señal de plataforma solo por HTML, no confirmada por API — requiere investigación manual adicional."]

    if hit_strong_waf:
        return "ROJO", notes + [f"WAF hostil sin plataforma identificable limpiamente: {sorted(report.waf_hits)}. Playwright sería último recurso, a justificar caso por caso."]

    if report.waf_hits:
        return "AMARILLO", notes + [f"WAF de borde detectado ({sorted(report.waf_hits)}) pero no necesariamente bloqueante — validar con más requests."]

    return "ROJO", notes + ["No se identificó plataforma ni señal clara. Requiere investigación manual."]


def report_to_row(r: DomainReport) -> dict[str, str]:
    proteccion = ", ".join(r.waf_hits) if r.waf_hits else "ninguna detectada"
    if r.error:
        proteccion = f"error de red: {r.error}"
    requiere_region = "sí (VTEX regionId/sales channel)" if r.platform == "VTEX" else (
        "por confirmar" if r.platform not in ("DESCONOCIDA",) else "N/A"
    )
    return {
        "dominio": r.domain,
        "plataforma": r.platform,
        "endpoint_util": r.useful_endpoint or "—",
        "proteccion": proteccion,
        "requiere_region": requiere_region,
        "viabilidad": r.viability,
        "notas": " | ".join(r.notes) if r.notes else "",
    }


def render_markdown_table(rows: list[dict[str, str]]) -> str:
    headers = ["dominio", "plataforma", "endpoint_util", "proteccion", "requiere_region", "viabilidad", "notas"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row[h].replace("\n", " ").replace("|", "/") for h in headers) + " |")
    return "\n".join(lines)


DEFAULT_DOMAINS = [
    # Autoservicio
    "chedraui.com.mx",
    "soriana.com",
    "lacomer.com.mx",
    "heb.com.mx",
    "super.walmart.com.mx",
    "bodegaaurrera.com.mx",
    "sams.com.mx",
    "costco.com.mx",
    "cityclub.com.mx",
    "tiendasneto.com",
    "merza.com.mx",
    "waldos.com.mx",
    "tiendasdax.com",
    # Conveniencia
    "oxxo.com",
    "7-eleven.com.mx",
    "circulok.com.mx",
    # Farmacia/mixto
    "farmaciasguadalajara.com",
    "benavides.com.mx",
    # Agregadores (plan C)
    "rappi.com.mx",
    "cornershopapp.com",
]


MAX_CONCURRENT_DOMAINS = 6  # limita contención del resolver DNS (notable en Windows)


async def main_async(domains: list[str]) -> list[DomainReport]:
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=10)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "es-MX,es;q=0.9"}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOMAINS)

    async def _bounded(d: str) -> DomainReport:
        async with semaphore:
            return await fingerprint_domain(client, d)

    async with httpx.AsyncClient(headers=headers, limits=limits) as client:
        # Cada dominio ya se auto-limita a 1 req/s vía DomainBudget; el
        # semáforo además acota cuántos dominios distintos se resuelven/
        # conectan en paralelo, para no saturar el resolver DNS local.
        tasks = [_bounded(d) for d in domains]
        return await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domains", nargs="*", help="Dominios a analizar (default: lista de candidatos del proyecto)")
    parser.add_argument("--json", dest="json_out", help="Ruta para volcar el reporte crudo en JSON")
    args = parser.parse_args()

    domains = args.domains or DEFAULT_DOMAINS
    reports = asyncio.run(main_async(domains))

    rows = [report_to_row(r) for r in reports]
    print(render_markdown_table(rows))

    if args.json_out:
        raw = []
        for r in reports:
            raw.append({
                "domain": r.domain,
                "platform": r.platform,
                "useful_endpoint": r.useful_endpoint,
                "waf_hits": r.waf_hits,
                "viability": r.viability,
                "notes": r.notes,
                "robots_blocks_api": r.robots_blocks_api,
                "error": r.error,
                "probes": {
                    name: {
                        "url": p.url,
                        "status": p.status,
                        "error": p.error,
                        "elapsed_ms": p.elapsed_ms,
                        "headers": p.headers,
                        "cookies": p.cookies,
                        "body_snippet": p.body_snippet[:1500],
                    }
                    for name, p in r.probes.items()
                },
            })
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)
        print(f"\nReporte crudo guardado en {args.json_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
