from __future__ import annotations

from typing import Dict, Tuple, List, Set, Optional
import re
from html import unescape
from bs4 import BeautifulSoup


# =========================
# TEXT UTILS
# =========================

_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")
_ZW_RE = re.compile(r"[\u200b\u200c\u200d\uFEFF]")  # zero-width


def _clean_text(s: str) -> str:
    """
    Нормализация текста:
    - decode html entities
    - убираем zero-width
    - нормализуем пробелы/переводы строк
    - trim
    """
    if not s:
        return ""
    s = unescape(s)
    s = _ZW_RE.sub("", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _WS_RE.sub(" ", s)
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)  # пробелы вокруг \n
    s = _NL_RE.sub("\n\n", s)
    return s.strip()


def _norm_key(s: str) -> str:
    """Ключ для дедупа: lower + схлопывание пробелов + лёгкая нормализация разделителей."""
    s = _clean_text(s).lower()
    s = re.sub(r"[•·▪●]+", " ", s)
    s = re.sub(r"[\s\u00a0]+", " ", s)
    return s.strip()


def _unique_key(name: str, section: Optional[str], seen: Set[str]) -> str:
    base = name.strip()
    nk = _norm_key(base)
    if nk not in seen:
        seen.add(nk)
        return base

    if section:
        candidate = f"{section} - {base}"
        nk2 = _norm_key(candidate)
        if nk2 not in seen:
            seen.add(nk2)
            return candidate

    i = 2
    while True:
        candidate = f"{base} ({i})"
        nk2 = _norm_key(candidate)
        if nk2 not in seen:
            seen.add(nk2)
            return candidate
        i += 1


def _register_key(name: str, seen: Set[str]) -> Optional[str]:
    base = name.strip()
    nk = _norm_key(base)
    if not nk:
        return None
    if nk in seen:
        return None
    seen.add(nk)
    return base


def _html_text(s: str) -> str:
    """
    Чистим html-кусок до текста:
    - убираем теги
    - decode html entities
    - нормализуем пробелы
    """
    if not s:
        return ""
    s = unescape(s)
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</p>\s*<p[^>]*>", "\n\n", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    return _clean_text(s)


# =========================
# URL UTILS
# =========================

def _abs_url(url: str, base_url: Optional[str]) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if base_url and url.startswith("/"):
        return base_url.rstrip("/") + url
    return url


# =========================
# IMAGES
# =========================

_RESTORE_MAIN_IMG_RE = re.compile(
    r'(?is)<img[^>]+class="[^"]*slides-swiper__main-image[^"]*"[^>]+src="([^"]+)"'
)
_RESTORE_GALLERY_BLOCK_RE = re.compile(
    r'(?is)<div[^>]+class="[^"]*detail__gallery[^"]*"[^>]*>(.*?)</div>'
)
_RESTORE_RESIZE_RE = re.compile(r"(?is)/resize_cache/iblock/([^/]+)/\\d+_\\d+_[^/]+/([^/]+)$")

# 1) src / data-src / data-original / content (og:image)
_IMG_URL_RES = [
    re.compile(r'(?is)<img[^>]+(?:src|data-src|data-original)\s*=\s*"([^"]+)"'),
    re.compile(r"(?is)<img[^>]+(?:src|data-src|data-original)\s*=\s*'([^']+)'"),
    re.compile(r'(?is)<meta[^>]+property\s*=\s*"og:image"[^>]+content\s*=\s*"([^"]+)"'),
    re.compile(r"(?is)<meta[^>]+property\s*=\s*'og:image'[^>]+content\s*=\s*'([^']+)'"),
]

# 2) часто картинки лежат в section-gallery-wrapper или swiper
_IMG_PRIOR_BLOCKS = [
    re.compile(r'(?is)<span[^>]+class="[^"]*section-gallery-wrapper[^"]*"[^>]*>(.*?)</span>'),
    re.compile(r'(?is)<div[^>]+class="[^"]*(?:swiper|gallery|product-gallery)[^"]*"[^>]*>(.*?)</div>'),
]


def extract_restore_image_urls_from_html(html: str, base_url: Optional[str] = None, limit: int = 50) -> List[str]:
    """
    Достаём URL картинок (по возможности только из "галерейных" блоков, иначе - по всему html).
    Возвращает уникальные ссылки с сохранением порядка.
    """
    if not html:
        return []

    def _norm_img_key(url: str) -> str:
        u = url.strip()
        m = _RESTORE_RESIZE_RE.search(u)
        if m:
            return f"/upload/iblock/{m.group(1)}/{m.group(2)}"
        return _norm_key(u)

    def _is_thumb(url: str) -> bool:
        return "/80_80_" in url or "/resize_cache/iblock" in url and "/80_80_" in url

    # 0) Пробуем взять только основные изображения из детальной галереи
    gallery_chunks = [html]
    m_gallery = _RESTORE_GALLERY_BLOCK_RE.search(html)
    if m_gallery and m_gallery.group(1):
        gallery_chunks = [m_gallery.group(1)]

    main_imgs: List[str] = []
    seen_main: Set[str] = set()
    for chunk in gallery_chunks:
        for raw in _RESTORE_MAIN_IMG_RE.findall(chunk):
            url = _abs_url(_clean_text(raw), base_url)
            if not url or _is_thumb(url):
                continue
            key = _norm_img_key(url)
            if key in seen_main:
                continue
            seen_main.add(key)
            main_imgs.append(url)
            if len(main_imgs) >= limit:
                return main_imgs

    if main_imgs:
        return main_imgs

    chunks: List[str] = []

    # ✅ собираем ВСЕ найденные блоки (а не только первый search)
    for brx in _IMG_PRIOR_BLOCKS:
        for m in brx.finditer(html):
            inner = m.group(1)
            if inner:
                chunks.append(inner)

    # если галерейные блоки не нашли — парсим весь html
    if not chunks:
        chunks = [html]

    seen: Set[str] = set()
    out: List[str] = []

    for chunk in chunks:
        for rx in _IMG_URL_RES:
            for raw in rx.findall(chunk):
                url = _abs_url(_clean_text(raw), base_url)
                if not url:
                    continue
                if _is_thumb(url):
                    continue
                k = _norm_img_key(url)
                if k in seen:
                    continue
                seen.add(k)
                out.append(url)
                if len(out) >= limit:
                    return out

    return out


# =========================
# SPECS (name -> value)
# =========================

# Основная таблица re-store: property + value
# Примеры типовые:
#   <span class="re-specs-table__text-property">Диагональ</span>
#   <span class="re-specs-table__text-value">6.1"</span>
_SPECS_PAIR_PRIMARY_RE = re.compile(
    r'(?is)re-specs-table__text-property"[^>]*>\s*([^<]+?)\s*<.*?'
    r're-specs-table__(?:text-value|value)"[^>]*>\s*(.*?)\s*<',
)

# Fallback: dt/dd, либо "name/value" в таблице
_SPECS_PAIR_FALLBACK_RES = [
    # re-store: property/value blocks
    re.compile(
        r'(?is)re-specs-table__property"[^>]*>.*?re-specs-table__text-property"[^>]*>\s*(.*?)\s*<.*?'
        r're-specs-table__value"[^>]*>\s*(.*?)\s*<'
    ),
    # <dt>name</dt><dd>value</dd>
    re.compile(r"(?is)<dt[^>]*>\s*(.*?)\s*</dt>\s*<dd[^>]*>\s*(.*?)\s*</dd>"),
    # <tr><td class="...name...">name</td><td class="...value...">value</td></tr>
    re.compile(
        r'(?is)<tr[^>]*>\s*<t[dh][^>]*class="[^"]*(?:name|prop|property)[^"]*"[^>]*>\s*(.*?)\s*</t[dh]>\s*'
        r'<t[dh][^>]*class="[^"]*(?:value|val)[^"]*"[^>]*>\s*(.*?)\s*</t[dh]>\s*</tr>'
    ),
]


def extract_restore_specs_from_html(html: str) -> Dict[str, str]:
    """
    Достаём характеристики как словарь: { "Диагональ": '6.1"' , ... }
    Дедуп по нормализованному имени. Пустые значения пропускаем.
    """
    if not html:
        return {}

    out: Dict[str, str] = {}
    seen: Dict[str, int] = {}

    # DOM parse for dynamic markup (основной путь)
    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select(".re-specs-table__row")
        for row in rows:
            k_el = row.select_one(".re-specs-table__text-property")
            if not k_el:
                continue

            v_el = row.select_one(".re-specs-table__value, .re-specs-table__text-value")
            if not v_el:
                v_el = row.select_one(".list--specs")

            k = _clean_text(k_el.get_text(" ", strip=True))

            if v_el is not None and v_el.name == "ul":
                items = [li.get_text(" ", strip=True) for li in v_el.select("li") if li.get_text(strip=True)]
                v = _clean_text("; ".join(items))
            elif v_el is not None:
                v = _clean_text(v_el.get_text(" ", strip=True))
            else:
                # последний шанс: берём текст строки без ключа
                row_text = _clean_text(row.get_text(" ", strip=True))
                if row_text.startswith(k):
                    v = _clean_text(row_text[len(k):].lstrip(" :—-"))
                else:
                    v = _clean_text(row_text.replace(k, "", 1).lstrip(" :—-"))

            if not k or not v:
                continue
            key = _register_key(k, seen)
            if key:
                out[key] = v
    except Exception:
        pass

    if out:
        return out

    # Regex fallback (если DOM пустой)
    pairs = _SPECS_PAIR_PRIMARY_RE.findall(html)
    if not pairs:
        for rx in _SPECS_PAIR_FALLBACK_RES:
            pairs = rx.findall(html)
            if pairs:
                break

    for raw_k, raw_v in pairs:
        k = _html_text(raw_k)
        v = _html_text(raw_v)
        if not k or not v:
            continue

        key = _register_key(k, seen)
        if key:
            out[key] = v

    return out


def extract_restore_spec_keys_from_html(html: str) -> List[str]:
    """
    Возвращает список названий параметров без значений.
    Используется для маппинга, когда значения не нужны.
    """
    if not html:
        return []

    meta = extract_restore_spec_meta_from_html(html)
    if meta:
        return [m["name"] for m in meta if m.get("name")]

    seen: Set[str] = set()
    out: List[str] = []
    rx = re.compile(r'(?is)re-specs-table__text-property"[^>]*>\s*([^<]+?)\s*<')
    for raw_k in rx.findall(html):
        k = _html_text(raw_k)
        if not k:
            continue
        nk = _norm_key(k)
        if nk in seen:
            continue
        seen.add(nk)
        out.append(k)

    return out


def extract_restore_spec_meta_from_html(html: str) -> List[Dict[str, str]]:
    """
    Возвращает мета по параметрам: name (оригинал), section (если есть), key (уникальный).
    """
    if not html:
        return []

    seen: Set[str] = set()
    out: List[Dict[str, str]] = []

    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select(".re-specs-table__row")
        for row in rows:
            k_el = row.select_one(".re-specs-table__text-property")
            if not k_el:
                continue
            name = _clean_text(k_el.get_text(" ", strip=True))
            if not name:
                continue

            section = ""
            sec = row.find_parent(class_="re-specs-table__section")
            if sec:
                name_el = sec.select_one(".re-specs-table__section-name")
                if name_el:
                    section = _clean_text(name_el.get_text(" ", strip=True))

            key = _unique_key(name, section or None, seen)
            out.append({"name": name, "section": section or "", "key": key})
    except Exception:
        pass

    if out:
        return out

    # Regex fallback without sections
    rx = re.compile(r'(?is)re-specs-table__text-property"[^>]*>\s*([^<]+?)\s*<')
    for raw_k in rx.findall(html):
        name = _html_text(raw_k)
        if not name:
            continue
        key = _unique_key(name, None, seen)
        out.append({"name": name, "section": "", "key": key})

    return out


def build_restore_spec_meta(items: List[Tuple[str, str]]) -> List[Dict[str, str]]:
    """
    Собирает мета-данные из пар (name, section) с уникальным key.
    """
    seen: Set[str] = set()
    out: List[Dict[str, str]] = []
    for name, section in items:
        name = _clean_text(name)
        section = _clean_text(section or "")
        if not name:
            continue
        key = _unique_key(name, section or None, seen)
        out.append({"name": name, "section": section, "key": key})
    return out


# =========================
# DESCRIPTION
# =========================

# Пытаемся найти описание в типовых контейнерах
_DESC_BLOCK_RES = [
    re.compile(r'(?is)<div[^>]+class="[^"]*(?:re-description|description|product-description|text|content)[^"]*"[^>]*>(.*?)</div>'),
    re.compile(r'(?is)<section[^>]+class="[^"]*(?:description|product-description|content)[^"]*"[^>]*>(.*?)</section>'),
    re.compile(r'(?is)<article[^>]+class="[^"]*(?:description|content)[^"]*"[^>]*>(.*?)</article>'),
]

# Иногда описание лежит в meta description / og:description
_META_DESC_RE = re.compile(
    r'(?is)<meta[^>]+(?:name|property)\s*=\s*"(?:description|og:description)"[^>]+content\s*=\s*"([^"]+)"'
)


def extract_restore_description_from_html(html: str) -> str:
    """
    Достаём текст описания.
    Сначала ищем блоки description, иначе — meta description.
    """
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
        scoped = soup.select_one(
            ".tab-content--description, .js-tab-descript, .rich.prerender-rich"
        )
        if scoped:
            descr = scoped.select_one(".product-descr") or scoped
            txt = " ".join(descr.get_text(" ", strip=True).split())
            if txt:
                return txt
    except Exception:
        pass

    for rx in _DESC_BLOCK_RES:
        m = rx.search(html)
        if m:
            txt = _html_text(m.group(1))
            if txt:
                return txt

    m = _META_DESC_RE.search(html)
    if m:
        return _clean_text(m.group(1))

    return ""


# =========================
# ONE-SHOT HELPER
# =========================

def extract_restore_product_content_from_html(
    html: str,
    base_url: Optional[str] = None,
) -> Tuple[List[str], Dict[str, str], str]:
    """
    Утилита "одним вызовом":
      images, specs, description
    """
    images = extract_restore_image_urls_from_html(html, base_url=base_url)
    specs = extract_restore_specs_from_html(html)
    desc = extract_restore_description_from_html(html)
    return images, specs, desc
