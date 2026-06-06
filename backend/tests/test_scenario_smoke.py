from __future__ import annotations

import importlib.util
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
