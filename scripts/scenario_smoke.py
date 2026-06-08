#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import ssl
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import Request, build_opener
from urllib.request import HTTPSHandler


DEFAULT_BASE_URL = "https://pim.id-smart.ru"
DEFAULT_ROUTES = (
    ("/catalog/exchange?tab=import", ("Импорт / Экспорт", "Импорт товаров")),
    ("/catalog/exchange?tab=export", ("Экспорт товаров", "Цели экспорта")),
    ("/sources?tab=categories", ("Сопоставления", "Маршрут сопоставления")),
    ("/admin/invites", ("Приглашения", "НОВОЕ ПРИГЛАШЕНИЕ")),
    ("/admin/status", ("Состояние системы", "Workflow runs")),
)
DEFAULT_PRODUCT_FLOW_CATEGORY_ID = "12547e4d-7713-414e-8aaf-a2fe919e1d3d"
DEFAULT_PRODUCT_FLOW_PRODUCT_ID = "product_70"
DEFAULT_PRODUCT_FLOW_SKU_MARKER = "50001"
DEFAULT_PRODUCT_FLOW_PARAMETER = "Процессор"
DEFAULT_PRODUCT_FLOW_VALUE_PARAMETER = ""
TECHNICAL_TEMPLATE_LABEL_RE = re.compile(r"\b(?:Draft|Template|Model):\s*[0-9a-f]{8}-[0-9a-f-]{27,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.has_root = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        if attrs_map.get("id") == "root":
            self.has_root = True
        if tag == "script":
            src = attrs_map.get("src", "")
            if src:
                self.scripts.append(src)
        if tag == "link" and attrs_map.get("rel") == "stylesheet":
            href = attrs_map.get("href", "")
            if href:
                self.styles.append(href)


def normalize_base_url(value: str | None) -> str:
    base = (value or DEFAULT_BASE_URL).strip().rstrip("/")
    if not base:
        return DEFAULT_BASE_URL
    if not base.startswith(("http://", "https://")):
        return f"https://{base}"
    return base


def parse_vite_assets(html: str) -> tuple[bool, list[str]]:
    parser = AssetParser()
    parser.feed(html)
    assets = [*parser.scripts, *parser.styles]
    return parser.has_root, assets


def result_status(results: Iterable[CheckResult]) -> int:
    return 0 if all(item.ok for item in results) else 1


def build_product_flow_routes(
    category_id: str,
    product_id: str,
    sku_marker: str,
    focus_parameter: str = "",
    focus_value_parameter: str = "",
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    category = quote(str(category_id or "").strip(), safe="")
    product = quote(str(product_id or "").strip(), safe="")
    sku = str(sku_marker or "").strip()
    parameter = str(focus_parameter or "").strip()
    parameter_q = quote(parameter, safe="") if parameter else ""
    value_parameter = str(focus_value_parameter or "").strip()
    value_parameter_q = quote(value_parameter, safe="") if value_parameter else ""
    if not category or not product:
        return ()
    product_markers = ("ПАРАМЕТРЫ PIM", "Параметры и значения", "Медиа", sku) if sku else ("ПАРАМЕТРЫ PIM", "Параметры и значения", "Медиа")
    export_markers = ("Экспорт товаров", "Я.Маркет", "OZON", sku) if sku else ("Экспорт товаров", "Я.Маркет", "OZON")
    routes: list[tuple[str, tuple[str, ...]]] = [
        ("/", ("Рабочая сводка", "Открыть товары")),
        (f"/templates/{category}", ("Инфо-модели", "К сопоставлениям")),
        (f"/sources?tab=params&category={category}&product={product}", ("Сопоставления", "Черновик характеристик PIM")),
        (f"/sources?tab=values&category={category}&product={product}", ("Сопоставления", "Значения")),
        (f"/products/{product}?tab=attributes", product_markers),
        (f"/catalog/exchange?tab=export&product={product}", export_markers),
    ]
    if parameter_q:
        routes.extend(
            [
                (
                    f"/sources?tab=params&category={category}&product={product}&parameter={parameter_q}&provider=ozon",
                    ("Сопоставления", parameter),
                ),
                (
                    f"/products/{product}?tab=attributes&parameter={parameter_q}",
                    (*product_markers, parameter),
                ),
            ]
        )
    if value_parameter_q:
        routes.append(
            (
                f"/sources?tab=values&category={category}&product={product}&parameter={value_parameter_q}&provider=ozon",
                ("Сопоставления", "Значения для выгрузки", "полей для проверки", value_parameter),
            )
        )
    return tuple(routes)


def validate_export_latest_run(payload: dict[str, Any]) -> CheckResult:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    run_id = str(run.get("id") or "").strip()
    batches = run.get("batches") if isinstance(run.get("batches"), list) else []
    summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
    if payload.get("ok") is not True or not run_id:
        return CheckResult("export latest run", False, "latest run response is missing")
    if not batches:
        return CheckResult("export latest run", False, f"{run_id}: no batches")
    blockers: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        for blocker in batch.get("blockers") if isinstance(batch.get("blockers"), list) else []:
            if not isinstance(blocker, dict):
                continue
            blockers.append(blocker)
            details.extend([item for item in (blocker.get("missing_details") or []) if isinstance(item, dict)])
    blocked = int(summary.get("blocked_target_items") or 0)
    ready = int(summary.get("ready_target_items") or 0)
    if blocked > 0:
        if not blockers:
            return CheckResult("export latest run", False, f"{run_id}: summary has blockers but blocker rows are empty")
        if not details:
            return CheckResult("export latest run", False, f"{run_id}: blockers have no machine-readable missing_details")
        missing_fix = [
            str(detail.get("code") or detail.get("message") or "unknown")
            for detail in details
            if not str(detail.get("fix_href") or "").strip() or not str(detail.get("fix_label") or "").strip()
        ]
        if missing_fix:
            return CheckResult("export latest run", False, f"{run_id}: blocker fix links missing for {', '.join(missing_fix[:5])}")
        missing_context: list[str] = []
        for detail in details:
            fix_href = str(detail.get("fix_href") or "").strip()
            if not fix_href:
                continue
            parsed = urlparse(fix_href)
            params = parse_qs(parsed.query)
            expected_fields = {
                "category_id": str((params.get("category") or [""])[0] or "").strip(),
                "product_id": str((params.get("product") or [""])[0] or "").strip(),
                "provider": str((params.get("provider") or [""])[0] or "").strip(),
            }
            for field, expected in expected_fields.items():
                if expected and str(detail.get(field) or "").strip() != expected:
                    missing_context.append(f"{detail.get('code') or 'unknown'}:{field}")
        if missing_context:
            return CheckResult("export latest run", False, f"{run_id}: blocker fix context missing for {', '.join(missing_context[:5])}")
    elif ready <= 0:
        return CheckResult("export latest run", False, f"{run_id}: no ready or blocked target rows")
    return CheckResult("export latest run", True, f"{run_id}: ready={ready}, blocked={blocked}, batches={len(batches)}")


def validate_product_queue_labels(body: str, sku_marker: str = "") -> CheckResult:
    text = str(body or "")
    if TECHNICAL_TEMPLATE_LABEL_RE.search(text):
        return CheckResult("product queue labels", False, "technical Draft/Template UUID label is visible")
    visible_scope = "visible queue" if not sku_marker or sku_marker in text else "visible queue; smoke SKU is checked on product route"
    if "Инфо-модель:" in text:
        return CheckResult("product queue labels", True, f"technical template labels hidden; readable model label visible in {visible_scope}")
    if "Собрать модель" in text or "НЕТ ИНФО-МОДЕЛИ" in text:
        return CheckResult("product queue labels", True, f"technical template labels hidden; missing model CTA visible in {visible_scope}")
    return CheckResult("product queue labels", False, "neither readable model label nor missing-model CTA is visible")


def validate_legacy_competitor_redirect_url(url: str, category_id: str, product_id: str) -> CheckResult:
    text = str(url or "")
    if "/sources?" not in text or "tab=sources" not in text:
        return CheckResult("legacy competitor redirect", False, f"unexpected target: {text}")
    if category_id and f"category={quote(category_id, safe='')}" not in text:
        return CheckResult("legacy competitor redirect", False, "category context is missing")
    if product_id and f"product={quote(product_id, safe='')}" not in text:
        return CheckResult("legacy competitor redirect", False, "product context is missing")
    return CheckResult("legacy competitor redirect", True, "category and product context preserved")


def is_ignorable_browser_console_error(message: str) -> bool:
    transient_network_markers = ("net::ERR_CONNECTION_CLOSED",)
    return any(marker in message for marker in transient_network_markers)


def parse_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return max(1, int(raw_value))
    except ValueError:
        return default


def print_results(results: Iterable[CheckResult]) -> None:
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        suffix = f" - {result.detail}" if result.detail else ""
        print(f"[{marker}] {result.name}{suffix}")


class HttpClient:
    def __init__(self, base_url: str, timeout: int, *, insecure_ssl: bool = False, retries: int | None = None) -> None:
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        if retries is None:
            retries = parse_positive_int_env("SMARTPIM_SMOKE_HTTP_RETRIES", 3)
        self.retries = max(1, retries)
        if insecure_ssl:
            self.opener = build_opener(HTTPSHandler(context=ssl._create_unverified_context()))
        else:
            self.opener = build_opener()

    def get(self, path_or_url: str) -> tuple[int, str, str]:
        url = path_or_url if path_or_url.startswith(("http://", "https://")) else urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))
        request = Request(url, headers={"User-Agent": "SmartPIMScenarioSmoke/1.0"})
        last_error: URLError | None = None
        for attempt in range(self.retries):
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    content_type = response.headers.get("content-type", "")
                    return int(response.status), body, content_type
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                return int(exc.code), body, exc.headers.get("content-type", "")
            except URLError as exc:
                last_error = exc
                if attempt + 1 >= self.retries:
                    break
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
        if last_error is None:
            raise RuntimeError("request failed")
        raise RuntimeError(str(last_error.reason)) from last_error


def public_smoke(base_url: str, timeout: int, *, insecure_ssl: bool = False) -> list[CheckResult]:
    client = HttpClient(base_url, timeout, insecure_ssl=insecure_ssl)
    results: list[CheckResult] = []

    try:
        status, body, _ = client.get("/api/health")
        payload = json.loads(body)
        results.append(CheckResult("api health", status == 200 and payload.get("ok") is True, f"status={status}"))
    except Exception as exc:
        results.append(CheckResult("api health", False, str(exc)))

    try:
        status, html, _ = client.get("/")
        has_root, assets = parse_vite_assets(html)
        app_assets = [asset for asset in assets if "/assets/" in asset]
        results.append(CheckResult("spa shell", status == 200 and has_root and bool(app_assets), f"status={status}, assets={len(app_assets)}"))
    except Exception as exc:
        results.append(CheckResult("spa shell", False, str(exc)))
        app_assets = []

    for asset in app_assets[:5]:
        try:
            status, body, content_type = client.get(asset)
            is_asset = status == 200 and bool(body.strip()) and ("javascript" in content_type or "text/css" in content_type or asset.endswith((".js", ".css")))
            results.append(CheckResult(f"asset {asset}", is_asset, f"status={status}"))
        except Exception as exc:
            results.append(CheckResult(f"asset {asset}", False, str(exc)))

    for route, _markers in DEFAULT_ROUTES:
        try:
            status, html, _ = client.get(route)
            has_root, assets = parse_vite_assets(html)
            results.append(CheckResult(f"route shell {route}", status == 200 and has_root and bool(assets), f"status={status}, assets={len(assets)}"))
        except Exception as exc:
            results.append(CheckResult(f"route shell {route}", False, str(exc)))

    return results


async def browser_smoke(
    base_url: str,
    timeout: int,
    allow_auth_wall: bool,
    require_auth: bool,
    *,
    insecure_ssl: bool = False,
    extra_routes: Iterable[tuple[str, tuple[str, ...]]] = (),
    export_latest_product_id: str = "",
    product_queue_sku_marker: str = "",
    legacy_redirect_category_id: str = "",
    legacy_redirect_product_id: str = "",
) -> list[CheckResult]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return [CheckResult("browser runtime", False, "playwright is not installed")]

    base_url = normalize_base_url(base_url)
    email = os.environ.get("SMARTPIM_SMOKE_EMAIL", "").strip()
    password = os.environ.get("SMARTPIM_SMOKE_PASSWORD", "")
    results: list[CheckResult] = []
    console_errors: list[str] = []
    if require_auth and (not email or not password):
        return [CheckResult("browser credentials", False, "set SMARTPIM_SMOKE_EMAIL and SMARTPIM_SMOKE_PASSWORD")]

    async def goto_app_page(page: Any, url: str) -> None:
        nav_retries = parse_positive_int_env("SMARTPIM_SMOKE_BROWSER_NAV_RETRIES", 2)
        last_error: Exception | None = None
        for attempt in range(nav_retries):
            try:
                await page.goto(url, wait_until="domcontentloaded")
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt + 1 < nav_retries:
                    await asyncio.sleep(min(2.0, 0.5 * (attempt + 1)))
        if last_error is not None:
            raise last_error
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 5000))
        except Exception:
            pass

    async def page_body_after_markers(page: Any, markers: tuple[str, ...]) -> str:
        marker_wait_ms = parse_positive_int_env("SMARTPIM_SMOKE_MARKER_WAIT_MS", 15000)
        async def read_after_wait() -> str:
            body_now = await page.locator("body").inner_text()
            missing_now = [marker for marker in markers if marker not in body_now]
            if not missing_now:
                return body_now
            try:
                await page.wait_for_function(
                    """(markers) => {
                        const text = document.body?.innerText || "";
                        return markers.every((marker) => text.includes(marker));
                    }""",
                    list(markers),
                    timeout=marker_wait_ms,
                )
            except Exception:
                pass
            return await page.locator("body").inner_text()

        body = await read_after_wait()
        if any(marker not in body for marker in markers):
            try:
                await page.reload(wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=min(marker_wait_ms, 5000))
                except Exception:
                    pass
                body = await read_after_wait()
            except Exception:
                pass
        return body

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(ignore_https_errors=insecure_ssl, viewport={"width": 1600, "height": 1000})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type == "error" and not is_ignorable_browser_console_error(msg.text)
            else None,
        )
        page.set_default_timeout(timeout * 1000)

        if email and password:
            await goto_app_page(page, f"{base_url}/login")
            await page.fill('input[name="loginValue"], input[name="login"]', email)
            await page.fill('input[name="password"]', password)
            async with page.expect_response(lambda response: "/api/auth/login" in response.url, timeout=timeout * 1000):
                await page.click('button[type="submit"]')
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 5000))
            except Exception:
                pass
            try:
                await page.wait_for_url(lambda url: "/login" not in url, timeout=min(timeout * 1000, 5000))
            except Exception:
                pass
            body = await page.locator("body").inner_text()
            results.append(CheckResult("browser login", "Вход пользователя" not in body and "Ошибка входа" not in body, "env credentials"))
        elif require_auth:
            results.append(CheckResult("browser login", False, "credentials required"))

        for route, markers in (*DEFAULT_ROUTES, *tuple(extra_routes)):
            try:
                await goto_app_page(page, f"{base_url}{route}")
                body = await page_body_after_markers(page, markers)
                if "Вход пользователя" in body and not email:
                    ok = allow_auth_wall
                    detail = "auth wall; set SMARTPIM_SMOKE_EMAIL/SMARTPIM_SMOKE_PASSWORD for full route markers"
                elif "Вход пользователя" in body and require_auth:
                    ok = False
                    detail = "still on auth wall after login"
                else:
                    missing = [marker for marker in markers if marker not in body]
                    ok = not missing
                    detail = "ok" if ok else f"missing markers: {', '.join(missing)}"
                results.append(CheckResult(f"browser route {route}", ok, detail))
            except Exception as exc:
                results.append(CheckResult(f"browser route {route}", False, str(exc)))

        if product_queue_sku_marker:
            try:
                await goto_app_page(page, f"{base_url}/products")
                body = await page.locator("body").inner_text()
                if "Вход пользователя" in body and not email:
                    results.append(CheckResult("product queue labels", allow_auth_wall, "auth wall; credentials needed for label smoke"))
                elif "Вход пользователя" in body and require_auth:
                    results.append(CheckResult("product queue labels", False, "still on auth wall after login"))
                else:
                    results.append(validate_product_queue_labels(body, product_queue_sku_marker))
            except Exception as exc:
                results.append(CheckResult("product queue labels", False, str(exc)))

        if legacy_redirect_category_id or legacy_redirect_product_id:
            try:
                category = quote(str(legacy_redirect_category_id or "").strip(), safe="")
                product = quote(str(legacy_redirect_product_id or "").strip(), safe="")
                await goto_app_page(page, f"{base_url}/data-prep/competitors?category={category}&product={product}")
                results.append(
                    validate_legacy_competitor_redirect_url(
                        page.url,
                        str(legacy_redirect_category_id or "").strip(),
                        str(legacy_redirect_product_id or "").strip(),
                    )
                )
            except Exception as exc:
                results.append(CheckResult("legacy competitor redirect", False, str(exc)))

        if export_latest_product_id:
            try:
                product = quote(str(export_latest_product_id).strip(), safe="")
                latest_url = f"{base_url}/api/catalog/exchange/export/latest-run?product_id={product}"
                latest_timeout = parse_positive_int_env("SMARTPIM_SMOKE_EXPORT_LATEST_TIMEOUT_MS", max(timeout * 1000, 60000))
                latest_retries = parse_positive_int_env("SMARTPIM_SMOKE_EXPORT_LATEST_RETRIES", 2)
                last_error = ""
                for attempt in range(latest_retries):
                    try:
                        response = await page.request.get(latest_url, timeout=latest_timeout)
                        if response.status != 200:
                            results.append(CheckResult("export latest run", False, f"status={response.status}"))
                        else:
                            results.append(validate_export_latest_run(await response.json()))
                        last_error = ""
                        break
                    except Exception as exc:
                        last_error = str(exc)
                        if attempt + 1 < latest_retries:
                            await asyncio.sleep(min(2.0, 0.5 * (attempt + 1)))
                if last_error:
                    results.append(CheckResult("export latest run", False, last_error))
            except Exception as exc:
                results.append(CheckResult("export latest run", False, str(exc)))

        await browser.close()

    results.append(CheckResult("browser console", not console_errors, "; ".join(console_errors[:3])))
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SmartPIM release scenario smoke checks.")
    parser.add_argument("--base-url", default=os.environ.get("SMARTPIM_SMOKE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("SMARTPIM_SMOKE_TIMEOUT", "20")))
    parser.add_argument("--browser", action="store_true", default=os.environ.get("SMARTPIM_SMOKE_BROWSER") == "1")
    parser.add_argument("--allow-auth-wall", action="store_true", default=os.environ.get("SMARTPIM_SMOKE_ALLOW_AUTH_WALL") == "1")
    parser.add_argument("--require-auth", action="store_true", default=os.environ.get("SMARTPIM_SMOKE_REQUIRE_AUTH") == "1")
    parser.add_argument("--insecure-ssl", action="store_true", default=os.environ.get("SMARTPIM_SMOKE_INSECURE_SSL") == "1")
    parser.add_argument("--public-only", action="store_true", help="Skip browser checks even if SMARTPIM_SMOKE_BROWSER=1.")
    parser.add_argument("--product-flow", action="store_true", default=os.environ.get("SMARTPIM_SMOKE_PRODUCT_FLOW") == "1", help="Add catalog -> info-model -> product -> export browser route markers for one SKU.")
    parser.add_argument("--export-latest", action="store_true", default=os.environ.get("SMARTPIM_SMOKE_EXPORT_LATEST") == "1", help="After browser login, assert the latest saved export run for the smoke SKU has rows and actionable blockers.")
    parser.add_argument("--flow-category-id", default=os.environ.get("SMARTPIM_SMOKE_FLOW_CATEGORY_ID", DEFAULT_PRODUCT_FLOW_CATEGORY_ID))
    parser.add_argument("--flow-product-id", default=os.environ.get("SMARTPIM_SMOKE_FLOW_PRODUCT_ID", DEFAULT_PRODUCT_FLOW_PRODUCT_ID))
    parser.add_argument("--flow-sku-marker", default=os.environ.get("SMARTPIM_SMOKE_FLOW_SKU_MARKER", DEFAULT_PRODUCT_FLOW_SKU_MARKER))
    parser.add_argument("--flow-parameter", default=os.environ.get("SMARTPIM_SMOKE_FLOW_PARAMETER", DEFAULT_PRODUCT_FLOW_PARAMETER), help="Known PIM parameter used to verify focused product/params deep links.")
    parser.add_argument("--flow-value-parameter", default=os.environ.get("SMARTPIM_SMOKE_FLOW_VALUE_PARAMETER", DEFAULT_PRODUCT_FLOW_VALUE_PARAMETER), help="Known value-mapping field used to verify focused values deep links when the fixture has value rows.")
    return parser


async def async_main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    start = time.monotonic()
    results = public_smoke(args.base_url, args.timeout, insecure_ssl=args.insecure_ssl)
    if args.browser and not args.public_only:
        product_flow_routes = build_product_flow_routes(
            args.flow_category_id,
            args.flow_product_id,
            args.flow_sku_marker,
            args.flow_parameter,
            args.flow_value_parameter,
        ) if args.product_flow else ()
        results.extend(
            await browser_smoke(
                args.base_url,
                args.timeout,
                args.allow_auth_wall,
                args.require_auth,
                insecure_ssl=args.insecure_ssl,
                extra_routes=product_flow_routes,
                export_latest_product_id=args.flow_product_id if args.export_latest else "",
                product_queue_sku_marker=args.flow_sku_marker if args.product_flow else "",
                legacy_redirect_category_id=args.flow_category_id if args.product_flow else "",
                legacy_redirect_product_id=args.flow_product_id if args.product_flow else "",
            )
        )
    print_results(results)
    print(f"Smoke duration: {time.monotonic() - start:.1f}s")
    return result_status(results)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(list(argv or sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
