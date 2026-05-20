from __future__ import annotations

from typing import Dict, List, Tuple
import re
import html as _html
from urllib.parse import unquote, urljoin, urlparse
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


def extract_store77_title_from_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for selector in ("h1", "meta[property='og:title']", "title"):
        el = soup.select_one(selector)
        if not el:
            continue
        value = str(el.get("content") or el.get_text(" ", strip=True) or "").strip()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"^Купить\s+", "", value, flags=re.I).strip()
        value = re.split(r"\s+в Москве\b|\s+\|\s*Store77\b", value, maxsplit=1, flags=re.I)[0].strip()
        if value:
            return value
    return ""


def infer_store77_specs_from_title_or_url(title: str, url: str | None = None) -> Dict[str, str]:
    text = " ".join(part for part in (title, unquote(urlparse(url or "").path.replace("_", " "))) if part)
    normalized = text.lower().replace("ё", "е")
    out: Dict[str, str] = {}

    memory = re.search(r"\b(\d+)\s*(?:gb|гб|гб\.|gb\.|г\s*б)\b", normalized)
    if memory:
        out["Память"] = f"{memory.group(1)} ГБ"
    else:
        memory_tb = re.search(r"\b(\d+)\s*(?:tb|тб|т\s*б)\b", normalized)
        if memory_tb:
            out["Память"] = f"{memory_tb.group(1)} ТБ"

    color_match = re.search(r"цвет\s*:\s*([^,|]+)", title, re.I)
    if color_match:
        out["Цвет"] = color_match.group(1).strip()
    elif "soft pink" in normalized or "rozovyy" in normalized or "розов" in normalized:
        out["Цвет"] = "розовый (Soft pink)"
    elif "white" in normalized or "belyy" in normalized or "бел" in normalized:
        out["Цвет"] = "белый (White)"
    elif "black" in normalized or "chernyy" in normalized or "черн" in normalized:
        out["Цвет"] = "черный (Black)"

    if "nano sim" in normalized and "esim" in normalized:
        out["SIM-карта"] = "nano SIM + eSIM"
    elif "esim" in normalized or "elektronnaya sim karta" in normalized or "электронная sim" in normalized:
        out["SIM-карта"] = "eSIM"
    elif "dual sim" in normalized:
        out["SIM-карта"] = "Dual SIM"

    model_match = re.search(r"\biphone\s+(\d{1,2}\s*e|\d{1,2}(?:\s+(?:pro\s+max|pro|plus|mini))?)\b", normalized)
    if model_match:
        model = re.sub(r"\s+", " ", model_match.group(1)).strip()
        out["Модель"] = f"iPhone {model}"
    return out


_STORE77_GALLERY_BLOCK_RE = re.compile(
    r'(?is)<div[^>]+class="[^"]*wrap_gallery_card_main[^"]*"[^>]*>(.*?)</div>'
)
_STORE77_GALLERY_BLOCK_RE2 = re.compile(
    r'(?is)<div[^>]+id="cardPhoto"[^>]*>(.*?)</div>'
)
_STORE77_BG_URL_RE = re.compile(
    r'(?is)background-image\s*:\s*url\(([^)]+)\)'
)


def _clean_style_url(raw: str) -> str:
    s = _html.unescape(raw or "")
    s = s.strip().strip("\"' ")
    return s


def extract_store77_image_urls_from_html(html: str, base_url: str | None = None) -> List[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        src = _norm_img_url(_clean_style_url(raw), base_url)
        if not src:
            return
        lower = src.lower()
        if not re.search(r"\.(?:jpg|jpeg|png|webp)(?:[?#].*)?$", lower):
            return
        if "/upload/" not in lower and "/resize_cache/" not in lower:
            return
        if src in seen:
            return
        seen.add(src)
        urls.append(src)

    primary_roots = [
        *soup.select("#cardPhoto"),
        *soup.select("#image-popup-container .slick-offer-img-big"),
        *soup.select(".wrap_gallery_card_main"),
    ]
    secondary_roots = [
        *soup.select("#image-popup-container"),
        *soup.select(".modal_card_gallery"),
    ]
    roots = primary_roots or secondary_roots or [soup]
    for root in roots:
        for img in root.select("img"):
            for attr in ("data-src", "data-lazy", "src"):
                add(str(img.get(attr) or ""))
        for el in root.select("[style]"):
            style = str(el.get("style") or "")
            for match in _STORE77_BG_URL_RE.finditer(style):
                add(match.group(1))

    if not urls:
        for match in re.finditer(r"""(?i)(?:https?:)?//[^"'\s<>]+?\.(?:jpg|jpeg|png|webp)|/(?:upload|resize_cache)/[^"'\s<>]+?\.(?:jpg|jpeg|png|webp)""", html):
            add(match.group(0))
    return urls[:24]


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
    inferred_specs = infer_store77_specs_from_title_or_url(extract_store77_title_from_html(html), base_url)
    specs = {**inferred_specs, **specs}
    desc = extract_store77_description_from_html(html)
    return images, specs, desc
