from __future__ import annotations

from typing import Dict, List, Tuple
import re
import html as _html
from urllib.parse import urljoin
from bs4 import BeautifulSoup


def extract_store77_tabs(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    """
    Возвращает:
    {
      "Общие": {"Тип": "Смартфон", ...},
      "Экран": {"Диагональ": "6.9 дюйм", ...},
      ...
    }
    """
    out: Dict[str, Dict[str, str]] = {}

    root = soup.select_one("#cardOptions")
    if not root:
        return out

    # вкладки: href="#cardOption0", текст "Общие"...
    tab_titles: Dict[str, str] = {}
    for a in root.select('ul.nav.nav-tabs a[href^="#cardOption"]'):
        href = (a.get("href") or "").strip()
        title = " ".join(a.get_text(" ", strip=True).split())
        if href and title:
            tab_titles[href.lstrip("#")] = title

    # контент вкладок: div#cardOption0 ... table.tabs_table
    for pane in root.select('div.tab-content > div[id^="cardOption"]'):
        pane_id = (pane.get("id") or "").strip()
        if not pane_id:
            continue

        tab_name = tab_titles.get(pane_id) or pane_id
        specs: Dict[str, str] = {}

        table = pane.select_one("table.tabs_table")
        if not table:
            continue

        for tr in table.select("tr"):
            tds = tr.select("td")
            if len(tds) < 2:
                continue

            key = " ".join(tds[0].get_text(" ", strip=True).split())
            val = " ".join(tds[1].get_text(" ", strip=True).split())

            # чистим NBSP и мусор
            key = key.replace("\xa0", " ").strip()
            val = val.replace("\xa0", " ").strip()

            if key and val:
                specs[key] = val

        if specs:
            out[tab_name] = specs

    return out


def extract_store77_fields(soup: BeautifulSoup) -> List[str]:
    """
    Возвращает уникальный список названий характеристик (как они на сайте).
    """
    tabs = extract_store77_tabs(soup)
    fields = []
    seen = set()
    for _tab, kv in tabs.items():
        for k in kv.keys():
            if k not in seen:
                seen.add(k)
                fields.append(k)
    return fields


def _norm_img_url(src: str, base_url: str | None) -> str:
    s = (src or "").strip()
    if not s:
        return ""
    if s.startswith("//"):
        return "https:" + s
    if base_url:
        return urljoin(base_url, s)
    return s


def extract_store77_specs(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Возвращает плоский dict характеристик (без секций).
    """
    tabs = extract_store77_tabs(soup)
    out: Dict[str, str] = {}
    for _tab, kv in tabs.items():
        for k, v in kv.items():
            if k and k not in out:
                out[k] = v
    return out


_STORE77_GALLERY_BLOCK_RE = re.compile(
    r'(?is)<div[^>]+class="[^"]*wrap_gallery_card_main[^"]*"[^>]*>(.*?)</div>'
)
_STORE77_GALLERY_BLOCK_RE2 = re.compile(
    r'(?is)<div[^>]+id="cardPhoto"[^>]*>(.*?)</div>'
)
_STORE77_BG_URL_RE = re.compile(
    r'(?is)background-image\\s*:\\s*url\\(([^)]+)\\)'
)


def _clean_style_url(raw: str) -> str:
    s = _html.unescape(raw or "")
    s = s.strip().strip("\"' ")
    return s


def extract_store77_image_urls_from_html(html: str, base_url: str | None = None) -> List[str]:
    # По решению: изображения берём только из re-store.
    return []


def extract_store77_description_from_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    desc_root = soup.select_one(".card_bgsection__content") or soup.select_one(".card_bgsection")
    if desc_root:
        for el in desc_root.select(".card_descr_more_link"):
            el.decompose()
        wrap = desc_root.select_one(".wrap_descr_b") or desc_root
        txt = " ".join(wrap.get_text(" ", strip=True).split())
        if txt:
            return txt
    selectors = [
        ".wrap_descr_b",
        ".card_bgsection__content",
        "#description",
        ".product-description",
        ".card__description",
        "[itemprop='description']",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            txt = " ".join(el.get_text(" ", strip=True).split())
            if txt:
                return txt

    meta = soup.select_one("meta[name='description'], meta[property='og:description']")
    if meta and meta.get("content"):
        return " ".join(str(meta.get("content") or "").split())
    return ""


def extract_store77_product_content_from_html(
    html: str, base_url: str | None = None
) -> Tuple[List[str], Dict[str, str], str]:
    """
    Возвращает:
      images, specs, description
    """
    if not html:
        return [], {}, ""
    soup = BeautifulSoup(html, "html.parser")
    images = extract_store77_image_urls_from_html(html, base_url=base_url)
    specs = extract_store77_specs(soup)
    desc = extract_store77_description_from_html(html)
    return images, specs, desc
