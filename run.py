#!/usr/bin/env python
"""
Entrypoint del harvester diario. Lo llama el workflow de GitHub Actions
(cron + dispatch manual, Fase 6) — también se puede correr en local.

Uso:
    python run.py                    # todos los retailers activos en retailers/*.yaml
    python run.py --retailer chedraui  # solo ese (coincide con el nombre de archivo, sin .yaml)

Exit code:
    0  si todos los retailers activos corrieron y ninguna guarda de
       calidad bloqueante falló.
    1  si algún retailer falló en la corrida (excepción) o alguna guarda
       de calidad bloqueante falló para algún retailer — "fallar
       ruidosamente" es el requisito más importante de Fase 6
       (CLAUDE.md): un run que devuelve poco/nada en silencio es peor que
       un crash.

El resumen legible va a GITHUB_STEP_SUMMARY si la variable de entorno
existe (GitHub Actions la define sola); si no, se imprime a stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from core import pipeline
from core.config import load_all_retailer_configs, load_retailer_config


def _format_summary(all_results: list[dict], failures: list[str]) -> str:
    lines = ["# Resumen del harvester — botanas QRO", ""]
    if failures:
        lines.append(f"## ❌ {len(failures)} retailer(s) con problemas")
        for f in failures:
            lines.append(f"- {f}")
        lines.append("")
    else:
        lines.append("## ✅ Todo OK")
        lines.append("")

    for r in all_results:
        status_emoji = "✅" if not r.get("guards_failed") else "⚠️"
        lines.append(f"### {status_emoji} {r['retailer_name']}")
        lines.append("")
        lines.append(
            f"- Descubiertos: {r['discovered']} | En alcance: {r['in_scope']} "
            f"(excluidos por scope: {r['excluded_by_scope']})"
        )
        lines.append(
            f"- OK: {r['items_ok']} | Errores: {r['items_err']} | "
            f"Price events nuevos: {r['price_events_inserted']}"
        )
        lines.append(
            f"- needs_review: {r['needs_review']} | precio nulo/cero: {r['null_price']} | "
            f"tasa 403/429: {r['blocked_rate']:.1%}"
        )
        lines.append("")
        lines.append("| Guarda | Resultado | Detalle |")
        lines.append("|---|---|---|")
        for g in r["guard_results"]:
            if g.is_blocking:
                icon = "✅" if g.passed else "❌"
            else:
                icon = "ℹ️" if g.passed else "⚠️"
            lines.append(f"| {g.name} | {icon} | {g.message} |")
        lines.append("")

    return "\n".join(lines)


async def _run_all(retailer_name: str | None) -> int:
    if retailer_name:
        configs = [load_retailer_config(f"retailers/{retailer_name}.yaml")]
    else:
        configs = [c for c in load_all_retailer_configs() if c.active]

    if not configs:
        print("No hay retailers activos para correr.", file=sys.stderr)
        return 1

    all_results = []
    failures = []
    for config in configs:
        print(f"== Corriendo {config.name} ({config.platform}) ==")
        try:
            result = await pipeline.run_retailer(config)
        except Exception as exc:  # noqa: BLE001 — se reporta, no se re-lanza, para que otros retailers sigan corriendo
            failures.append(f"{config.name}: excepción durante el run — {exc}")
            print(f"  FALLÓ: {exc}", file=sys.stderr)
            continue

        all_results.append(result)
        if result["guards_failed"]:
            failed_guards = [g.name for g in result["guard_results"] if g.is_blocking and not g.passed]
            failures.append(f"{config.name}: guardas de calidad fallidas — {', '.join(failed_guards)}")
        print(
            f"  ok: descubiertos={result['discovered']} en_alcance={result['in_scope']} "
            f"items_ok={result['items_ok']} guardas={'FALLIDAS' if result['guards_failed'] else 'OK'}"
        )

    summary = _format_summary(all_results, failures)
    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with open(step_summary_path, "a", encoding="utf-8") as f:
            f.write(summary + "\n")
    else:
        print("\n" + summary)

    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retailer", help="Nombre del YAML en retailers/ (sin extensión) a correr — omitir para correr todos los activos")
    args = parser.parse_args()

    exit_code = asyncio.run(_run_all(args.retailer))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
