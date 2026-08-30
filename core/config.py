"""
Carga de configuración por retailer (retailers/<nombre>.yaml).

Agregar un retailer nuevo = agregar un archivo YAML aquí. Cero código
nuevo — ver CLAUDE.md, principio rector del proyecto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class RetailerConfig(BaseModel):
    name: str
    domain: str
    platform: str
    active: bool = True

    # --- Regionalización (Fase 2) ---
    sales_channel: str = "1"
    postal_code: str

    # --- Descubrimiento de categoría (Fase 3) ---
    category_paths: list[str] = Field(default_factory=list)
    """Rutas completas de categoría VTEX (fq=C:<path>), p.ej.
    "/1/107/10710/" — NO el id de hoja solo, ver hallazgo de Fase 3."""
    brand_seed: list[str] = Field(default_factory=list)
    generic_terms: list[str] = Field(default_factory=list)

    # --- Tráfico ---
    rate_limit_rps: float = 1.0
    timeout_s: float = 20.0

    # --- Overrides específicos del retailer que no ameritan código nuevo ---
    overrides: dict[str, Any] = Field(default_factory=dict)


def load_retailer_config(path: str | Path) -> RetailerConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RetailerConfig.model_validate(data)


def load_all_retailer_configs(retailers_dir: str | Path = "retailers") -> list[RetailerConfig]:
    retailers_dir = Path(retailers_dir)
    configs = []
    for yaml_path in sorted(retailers_dir.glob("*.yaml")):
        configs.append(load_retailer_config(yaml_path))
    return configs
