#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
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


def build_product_flow_routes(category_id: str, product_id: str, sku_marker: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    category = quote(str(category_id or "").strip(), safe="")
    product = quote(str(product_id or "").strip(), safe="")
    sku = str(sku_marker or "").strip()
    if not category or not product:
        return ()
    product_markers = ("Параметры PIM", "Медиа", sku) if sku else ("Параметры PIM", "Медиа")
    export_markers = ("Экспорт товаров", "Я.Маркет", "OZON", sku) if sku else ("Экспорт товаров", "Я.Маркет", "OZON")
    return (
        ("/", ("Рабочая сводка", "Открыть товары")),
        (f"/templates/{category}", ("Инфо-модели", "К сопоставлениям")),
        (f"/sources?tab=params&category={category}&product={product}", ("Сопоставления", "Черновик PIM-параметров")),
        (f"/sources?tab=values&category={category}&product={product}", ("Сопоставления", "Значения")),
        (f"/products/{product}?tab=attributes", product_markers),
        (f"/catalog/exchange?tab=export&product={product}", export_markers),
    )


def print_results(results: Iterable[CheckResult]) -> None:
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        suffix = f" - {result.detail}" if result.detail else ""
        print(f"[{marker}] {result.name}{suffix}")


class HttpClient:
    def __init__(self, base_url: str, timeout: int, *, insecure_ssl: bool = False) -> None:
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        if insecure_ssl:
            self.opener = build_opener(HTTPSHandler(context=ssl._create_unverified_context()))
        else:
            self.opener = build_opener()

    def get(self, path_or_url: str) -> tuple[int, str, str]:
        url = path_or_url if path_or_url.startswith(("http://", "https://")) else urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))
        request = Request(url, headers={"User-Agent": "SmartPIMScenarioSmoke/1.0"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                content_type = response.headers.get("content-type", "")
                return int(response.status), body, content_type
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return int(exc.code), body, exc.headers.get("content-type", "")
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc


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
        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 5000))
        except Exception:
            pass

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(ignore_https_errors=insecure_ssl)
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.set_default_timeout(timeout * 1000)

        if email and password:
            await goto_app_page(page, f"{base_url}/login")
            await page.fill('input[name="loginValue"]', email)
            await page.fill('input[name="password"]', password)
            await page.click('button[type="submit"]')
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 5000))
            except Exception:
                pass
            body = await page.locator("body").inner_text()
            results.append(CheckResult("browser login", "Вход пользователя" not in body and "Ошибка входа" not in body, "env credentials"))
        elif require_auth:
            results.append(CheckResult("browser login", False, "credentials required"))

        for route, markers in (*DEFAULT_ROUTES, *tuple(extra_routes)):
            try:
                await goto_app_page(page, f"{base_url}{route}")
                body = await page.locator("body").inner_text()
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
    parser.add_argument("--flow-category-id", default=os.environ.get("SMARTPIM_SMOKE_FLOW_CATEGORY_ID", DEFAULT_PRODUCT_FLOW_CATEGORY_ID))
    parser.add_argument("--flow-product-id", default=os.environ.get("SMARTPIM_SMOKE_FLOW_PRODUCT_ID", DEFAULT_PRODUCT_FLOW_PRODUCT_ID))
    parser.add_argument("--flow-sku-marker", default=os.environ.get("SMARTPIM_SMOKE_FLOW_SKU_MARKER", DEFAULT_PRODUCT_FLOW_SKU_MARKER))
    return parser


async def async_main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    start = time.monotonic()
    results = public_smoke(args.base_url, args.timeout, insecure_ssl=args.insecure_ssl)
    if args.browser and not args.public_only:
        product_flow_routes = build_product_flow_routes(args.flow_category_id, args.flow_product_id, args.flow_sku_marker) if args.product_flow else ()
        results.extend(
            await browser_smoke(
                args.base_url,
                args.timeout,
                args.allow_auth_wall,
                args.require_auth,
                insecure_ssl=args.insecure_ssl,
                extra_routes=product_flow_routes,
            )
        )
    print_results(results)
    print(f"Smoke duration: {time.monotonic() - start:.1f}s")
    return result_status(results)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(list(argv or sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
