from __future__ import annotations

import importlib.util
import asyncio
import sys
from pathlib import Path
from urllib.error import URLError


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


def test_http_client_retries_transient_url_errors(monkeypatch):
    class Response:
        status = 200
        headers = {"content-type": "text/plain"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"ok"

    class Opener:
        def __init__(self):
            self.calls = 0

        def open(self, _request, timeout):
            self.calls += 1
            if self.calls == 1:
                raise URLError("handshake timed out")
            return Response()

    sleeps: list[float] = []
    client = scenario_smoke.HttpClient("https://pim.example.test", 1)
    opener = Opener()
    client.opener = opener
    monkeypatch.setattr(scenario_smoke.time, "sleep", lambda value: sleeps.append(value))

    assert client.get("/login") == (200, "ok", "text/plain")
    assert opener.calls == 2
    assert sleeps


def test_browser_console_filter_only_ignores_transient_connection_closed():
    assert scenario_smoke.is_ignorable_browser_console_error(
        "Failed to load resource: net::ERR_CONNECTION_CLOSED"
    )
    assert not scenario_smoke.is_ignorable_browser_console_error("Uncaught TypeError: cannot read properties of undefined")
    assert not scenario_smoke.is_ignorable_browser_console_error("Failed to load resource: the server responded with a status of 500")


def test_parse_positive_int_env_uses_default_for_invalid_values(monkeypatch):
    monkeypatch.setenv("SMARTPIM_TEST_INT", "bad")
    assert scenario_smoke.parse_positive_int_env("SMARTPIM_TEST_INT", 7) == 7
    monkeypatch.setenv("SMARTPIM_TEST_INT", "0")
    assert scenario_smoke.parse_positive_int_env("SMARTPIM_TEST_INT", 7) == 1
    monkeypatch.setenv("SMARTPIM_TEST_INT", "12")
    assert scenario_smoke.parse_positive_int_env("SMARTPIM_TEST_INT", 7) == 12


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
        ("/products/product%2070?tab=attributes", ("ПАРАМЕТРЫ PIM", "Параметры и значения", "Медиа", "50001")),
        ("/catalog/exchange?tab=export&product=product%2070", ("Экспорт товаров", "Я.Маркет", "OZON", "50001")),
    )


def test_build_product_flow_routes_requires_category_and_product():
    assert scenario_smoke.build_product_flow_routes("", "product_70", "50001") == ()
    assert scenario_smoke.build_product_flow_routes("category", "", "50001") == ()


def test_validate_export_latest_run_requires_fix_links_for_blockers():
    result = scenario_smoke.validate_export_latest_run(
        {
            "ok": True,
            "run": {
                "id": "export_1",
                "summary": {"ready_target_items": 1, "blocked_target_items": 1},
                "batches": [
                    {
                        "blockers": [
                            {
                                "missing_details": [
                                    {"code": "value_mapping_required", "message": "Цвет не сопоставлен"}
                                ]
                            }
                        ]
                    }
                ],
            },
        }
    )

    assert result.ok is False
    assert "fix links missing" in result.detail


def test_validate_export_latest_run_accepts_ready_rows_without_blockers():
    result = scenario_smoke.validate_export_latest_run(
        {
            "ok": True,
            "run": {
                "id": "export_2",
                "summary": {"ready_target_items": 2, "blocked_target_items": 0},
                "batches": [{"blockers": []}],
            },
        }
    )

    assert result == scenario_smoke.CheckResult("export latest run", True, "export_2: ready=2, blocked=0, batches=1")


def test_validate_product_queue_labels_rejects_technical_template_names():
    result = scenario_smoke.validate_product_queue_labels(
        "Каталог товаров 50001 Draft: 12547e4d-7713-414e-8aaf-a2fe919e1d3d",
        "50001",
    )

    assert result.ok is False
    assert "technical" in result.detail


def test_validate_product_queue_labels_accepts_readable_template_names():
    result = scenario_smoke.validate_product_queue_labels(
        "Каталог товаров 50001 Инфо-модель: iPhone 16 Pro Max",
        "50001",
    )

    assert result == scenario_smoke.CheckResult(
        "product queue labels",
        True,
        "technical template labels hidden; readable model label visible",
    )


def test_validate_product_queue_labels_accepts_missing_model_cta():
    result = scenario_smoke.validate_product_queue_labels(
        "Каталог товаров 50001 ИНФО-МОДЕЛЬ Собрать модель НЕТ ИНФО-МОДЕЛИ",
        "50001",
    )

    assert result == scenario_smoke.CheckResult(
        "product queue labels",
        True,
        "technical template labels hidden; missing model CTA visible",
    )


def test_validate_legacy_competitor_redirect_url_requires_product_context():
    result = scenario_smoke.validate_legacy_competitor_redirect_url(
        "https://pim.example.test/sources?tab=sources&category=cat-phone",
        "cat-phone",
        "product_70",
    )

    assert result.ok is False
    assert "product context" in result.detail


def test_validate_legacy_competitor_redirect_url_accepts_canonical_source_target():
    result = scenario_smoke.validate_legacy_competitor_redirect_url(
        "https://pim.example.test/sources?tab=sources&category=cat-phone&product=product_70",
        "cat-phone",
        "product_70",
    )

    assert result == scenario_smoke.CheckResult(
        "legacy competitor redirect",
        True,
        "category and product context preserved",
    )
