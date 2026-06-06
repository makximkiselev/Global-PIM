from __future__ import annotations

import importlib.util
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE_PATH = ROOT / "scripts" / "scenario_smoke.py"
spec = importlib.util.spec_from_file_location("scenario_smoke", SMOKE_PATH)
assert spec and spec.loader
scenario_smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scenario_smoke
spec.loader.exec_module(scenario_smoke)


def test_normalize_base_url_adds_scheme_and_strips_trailing_slash():
    assert scenario_smoke.normalize_base_url("pim.example.test/") == "https://pim.example.test"
    assert scenario_smoke.normalize_base_url("http://localhost:5173/") == "http://localhost:5173"


def test_parse_vite_assets_reads_root_scripts_and_styles():
    html = """
    <html>
      <head>
        <script type="module" src="/assets/index-abc.js"></script>
        <link rel="stylesheet" href="/assets/index-def.css">
      </head>
      <body><div id="root"></div></body>
    </html>
    """
    has_root, assets = scenario_smoke.parse_vite_assets(html)
    assert has_root is True
    assert assets == ["/assets/index-abc.js", "/assets/index-def.css"]


def test_result_status_fails_when_any_check_failed():
    assert scenario_smoke.result_status([scenario_smoke.CheckResult("ok", True)]) == 0
    assert scenario_smoke.result_status(
        [scenario_smoke.CheckResult("ok", True), scenario_smoke.CheckResult("bad", False)]
    ) == 1


def test_browser_smoke_require_auth_fails_without_credentials(monkeypatch):
    monkeypatch.delenv("SMARTPIM_SMOKE_EMAIL", raising=False)
    monkeypatch.delenv("SMARTPIM_SMOKE_PASSWORD", raising=False)

    results = asyncio.run(scenario_smoke.browser_smoke("https://pim.example.test", 1, False, True, insecure_ssl=True))

    assert results == [
        scenario_smoke.CheckResult(
            "browser credentials",
            False,
            "set SMARTPIM_SMOKE_EMAIL and SMARTPIM_SMOKE_PASSWORD",
        )
    ]


def test_build_product_flow_routes_are_parameterized_and_escaped():
    routes = scenario_smoke.build_product_flow_routes("cat/id", "product 70", "50001")

    assert routes == (
        ("/", ("Рабочая сводка", "Открыть товары")),
        ("/templates/cat%2Fid", ("Инфо-модели", "К сопоставлениям")),
        ("/sources?tab=params&category=cat%2Fid&product=product%2070", ("Сопоставления", "Черновик PIM-параметров")),
        ("/sources?tab=values&category=cat%2Fid&product=product%2070", ("Сопоставления", "Значения")),
        ("/products/product%2070?tab=attributes", ("Параметры PIM", "Медиа", "50001")),
        ("/catalog/exchange?tab=export&product=product%2070", ("Экспорт товаров", "Я.Маркет", "OZON", "50001")),
    )


def test_build_product_flow_routes_requires_category_and_product():
    assert scenario_smoke.build_product_flow_routes("", "product_70", "50001") == ()
    assert scenario_smoke.build_product_flow_routes("category", "", "50001") == ()
