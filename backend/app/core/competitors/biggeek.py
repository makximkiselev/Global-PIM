from __future__ import annotations

from typing import Any, Dict, List
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _rub_price(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", raw)
    return digits or raw


def _label_from_slug(slug: str) -> str:
    normalized = str(slug or "").strip().lower()
    labels = {
        "esim": "eSIM",
        "nano-sim_i_esim": "nano-SIM и eSIM",
        "nano_sim_i_esim": "nano-SIM и eSIM",
        "nano-sim-esim": "nano-SIM и eSIM",
    }
    if normalized in labels:
        return labels[normalized]
    label = normalized.replace("_i_", " и ").replace("_", " ").replace("-", " ")
    label = label.replace("esim", "eSIM").replace("nano sim", "nano-SIM")
    return _text(label)


def _is_biggeek_product_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return (parsed.hostname or "").lower().endswith("biggeek.ru") and parsed.path.lower().startswith("/products/")


def _base_product_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return parsed._replace(fragment="").geturl().rstrip("/")


def _axis_name_for_item(item: Tag) -> str:
    axis = item.find_parent(class_=re.compile(r"prod-variant-picker__axis|prod-variant-picker-ssr"))
    if isinstance(axis, Tag):
        title = axis.select_one(".prod-info-price__group-title")
        if title:
            return _text(title.get_text(" ", strip=True))
    previous = item.find_previous(class_="prod-info-price__group-title")
    return _text(previous.get_text(" ", strip=True) if previous else "") or "Вариант"


def _label_for_item(item: Tag, slug: str) -> str:
    for selector in (".i-radio__text span", ".i-radio__text", ".beauty-text-wraping"):
        node = item.select_one(selector)
        label = _text(node.get_text(" ", strip=True) if node else "")
        if label:
            label = re.sub(r"\s*\?\s*$", "", label).strip()
            if label:
                return label
    return _label_from_slug(slug)


def extract_biggeek_variants_from_soup(page_url: str, soup: BeautifulSoup) -> List[Dict[str, Any]]:
    if not _is_biggeek_product_url(page_url):
        return []
    base_url = _base_product_url(page_url)
    if not base_url:
        return []
    variants: Dict[str, Dict[str, Any]] = {}

    for item in soup.select(".prod-info-price__check-item[data-slug]"):
        if not isinstance(item, Tag):
            continue
        slug = _text(item.get("data-slug"))
        if not slug:
            continue
        label = _label_for_item(item, slug)
        axis_name = _axis_name_for_item(item)
        price = _rub_price(item.get("data-price"))
        if not price:
            price_node = item.select_one(".prod-info-price__check-price")
            price = _rub_price(price_node.get_text(" ", strip=True) if price_node else "")
        variants.setdefault(
            slug,
            {
                "key": slug,
                "label": label or _label_from_slug(slug),
                "url": f"{base_url}#{slug}",
                "axis": axis_name,
                "price": price,
                "old_price": _rub_price(item.get("data-old-price")),
                "card_price": _rub_price(item.get("data-card-price")),
                "variation_id": _text(item.get("data-variation-id")),
                "specs": {axis_name: label or _label_from_slug(slug)} if axis_name else {},
            },
        )

    page_parsed = urlparse(page_url)
    base_path = page_parsed.path.rstrip("/")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        parsed = urlparse(href if href.startswith("http") else f"{base_url}{href if href.startswith('#') else ''}")
        if not parsed.fragment:
            continue
        if parsed.path and parsed.path.rstrip("/") not in {"", base_path}:
            continue
        slug = parsed.fragment
        if slug in variants:
            continue
        label = _text(anchor.get_text(" ", strip=True)) or _label_from_slug(slug)
        variants[slug] = {
            "key": slug,
            "label": label,
            "url": f"{base_url}#{slug}",
            "axis": "Вариант",
            "price": "",
            "old_price": "",
            "card_price": "",
            "variation_id": "",
            "specs": {"Вариант": label},
        }

    return list(variants.values())[:40]


def enrich_biggeek_content_for_variant(url: str, content: Dict[str, Any], soup: BeautifulSoup) -> Dict[str, Any]:
    parsed = urlparse(str(url or ""))
    slug = parsed.fragment
    if not slug:
        return content
    variants = extract_biggeek_variants_from_soup(url, soup)
    variant = next((item for item in variants if str(item.get("key") or "") == slug), None)
    if not variant:
        return content
    next_content = dict(content)
    specs = dict(next_content.get("specs") if isinstance(next_content.get("specs"), dict) else {})
    for key, value in (variant.get("specs") if isinstance(variant.get("specs"), dict) else {}).items():
        if _text(key) and _text(value):
            specs.setdefault(_text(key), _text(value))
    next_content["specs"] = specs
    if variant.get("price"):
        next_content["price"] = str(variant.get("price") or "")
    next_content["variant_key"] = str(variant.get("key") or "")
    next_content["variant_label"] = str(variant.get("label") or "")
    next_content["variant_axis"] = str(variant.get("axis") or "")
    return next_content
