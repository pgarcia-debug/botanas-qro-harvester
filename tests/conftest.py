import json
from pathlib import Path

import pytest

from core.config import RetailerConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def chedraui_config() -> RetailerConfig:
    return RetailerConfig(
        name="Chedraui",
        domain="www.chedraui.com.mx",
        platform="VTEX",
        sales_channel="1",
        postal_code="76000",
        category_paths=["/1/107/10710/"],
        brand_seed=["Sabritas"],
        generic_terms=["botana"],
        overrides={"requires_browser_like_headers": True},
    )
