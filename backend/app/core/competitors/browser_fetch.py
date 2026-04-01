from __future__ import annotations

import re
from playwright.async_api import async_playwright


async def fetch_html(url: str, timeout_ms: int = 45000) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        # минимальная анти-бот маскировка
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        # ускоряем загрузку: не грузим тяжелые ресурсы (но оставляем CSS для корректной разметки/ленивой подгрузки)
        async def _route(route):
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", _route)

        resp = None
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as e:
            await context.close()
            await browser.close()
            return f"__ERROR__:TIMEOUT__\n{e}"

        # re-store: ждём таблицу характеристик (если отрисовывается)
        try:
            await page.wait_for_selector(".re-specs-table", timeout=timeout_ms // 2)
            # дождаться рендера списка характеристик
            try:
                await page.wait_for_function(
                    "document.querySelectorAll('.re-specs-table__row').length > 20",
                    timeout=timeout_ms // 3,
                )
            except Exception:
                pass

            # прокрутка скролл-контейнера, чтобы подгрузить ленивые секции
            prev = 0
            stable = 0
            for _ in range(6):
                count = await page.evaluate(
                    "document.querySelectorAll('.re-specs-table__row').length"
                )
                if isinstance(count, int) and count <= prev:
                    stable += 1
                else:
                    stable = 0
                    prev = count if isinstance(count, int) else prev

                await page.evaluate(
                    """
                    () => {
                      const el = document.querySelector('[data-scroll-lock-scrollable]') ||
                                document.scrollingElement ||
                                document.documentElement;
                      if (el) el.scrollTop = el.scrollHeight;
                      window.scrollTo(0, document.body.scrollHeight);
                    }
                    """
                )
                await page.wait_for_timeout(800)
                if stable >= 2:
                    break

            # подождать, пока появится больше параметров
            try:
                await page.wait_for_function(
                    "document.querySelectorAll('.re-specs-table__text-property').length > 30",
                    timeout=timeout_ms // 3,
                )
            except Exception:
                pass
        except Exception:
            pass

        html = await page.content()
        status = None
        try:
            status = resp.status if resp else None
        except Exception:
            status = None
        # Простая диагностика защиты: сохраняем краткий лог, чтобы вернуть в UI.
        if status and status >= 400:
            html = f"__STATUS__:{status}__\n" + (html or "")
        await context.close()
        await browser.close()
        return html


async def fetch_restore_fields_meta(url: str, timeout_ms: int = 45000) -> list[dict]:
    """
    Возвращает список {name, section} напрямую из DOM в браузере.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        async def _route(route):
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", _route)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            await context.close()
            await browser.close()
            return []

        try:
            await page.wait_for_selector(".re-specs-table", timeout=timeout_ms // 2)
            # если есть кнопка "Показать все характеристики" — кликаем
            try:
                btn = (
                    page.locator(".tab-content--specs, .re-specs-table")
                    .get_by_text(re.compile(r"Показать|Все характеристики", re.I))
                    .first
                )
                if await btn.count() > 0:
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(800)
            except Exception:
                pass
            try:
                await page.wait_for_function(
                    "document.querySelectorAll('.re-specs-table__row').length > 20",
                    timeout=timeout_ms // 3,
                )
            except Exception:
                pass

            prev = 0
            stable = 0
            for _ in range(6):
                count = await page.evaluate(
                    "document.querySelectorAll('.re-specs-table__row').length"
                )
                if isinstance(count, int) and count <= prev:
                    stable += 1
                else:
                    stable = 0
                    prev = count if isinstance(count, int) else prev

                await page.evaluate(
                    """
                    () => {
                      const el = document.querySelector('[data-scroll-lock-scrollable]') ||
                                document.querySelector('.tabs__content') ||
                                document.scrollingElement ||
                                document.documentElement;
                      if (el) el.scrollTop = el.scrollHeight;
                      window.scrollTo(0, document.body.scrollHeight);
                    }
                    """
                )
                await page.wait_for_timeout(800)
                if stable >= 2:
                    break

            try:
                await page.wait_for_function(
                    "document.querySelectorAll('.re-specs-table__text-property').length > 30",
                    timeout=timeout_ms // 3,
                )
            except Exception:
                pass
        except Exception:
            pass

        try:
            items = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('.re-specs-table__row'))
                  .map(row => {
                    const nameEl = row.querySelector('.re-specs-table__text-property');
                    if (!nameEl) return null;
                    const name = (nameEl.textContent || '').trim();
                    const sec = row.closest('.re-specs-table__section');
                    const secNameEl = sec ? sec.querySelector('.re-specs-table__section-name') : null;
                    const section = secNameEl ? (secNameEl.textContent || '').trim() : '';
                    return name ? { name, section } : null;
                  })
                  .filter(Boolean);
                """
            )
        except Exception:
            items = []

        await context.close()
        await browser.close()
        return items or []


async def fetch_restore_specs_dom(url: str, timeout_ms: int = 45000) -> dict[str, str]:
    """
    Возвращает характеристики re-store напрямую из DOM (name -> value).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()

        async def _route(route):
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _route)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            await context.close()
            await browser.close()
            return {}

        try:
            await page.wait_for_selector(".re-specs-table", timeout=timeout_ms // 2)
            try:
                await page.wait_for_function(
                    "document.querySelectorAll('.re-specs-table__row').length > 20",
                    timeout=timeout_ms // 3,
                )
            except Exception:
                pass
        except Exception:
            pass

        try:
            items = await page.evaluate(
                """
                () => {
                  const rows = Array.from(document.querySelectorAll('.re-specs-table__row'));
                  const out = {};
                  for (const row of rows) {
                    const nameEl = row.querySelector('.re-specs-table__text-property');
                    if (!nameEl) continue;
                    const name = (nameEl.textContent || '').trim();
                    if (!name) continue;
                    let value = '';
                    const listEl = row.querySelector('.list--specs');
                    if (listEl) {
                      const items = Array.from(listEl.querySelectorAll('li'))
                        .map(li => (li.textContent || '').trim())
                        .filter(Boolean);
                      value = items.join('; ');
                    } else {
                      const valEl = row.querySelector('.re-specs-table__value, .re-specs-table__text-value');
                      value = valEl ? (valEl.textContent || '').trim() : '';
                    }
                    if (value && !(name in out)) out[name] = value;
                  }
                  return out;
                }
                """
            )
        except Exception:
            items = {}

        await context.close()
        await browser.close()
        return items or {}
