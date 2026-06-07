from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.storage.json_store import load_dict, save_dict


def normalize_value_key(value: Any) -> str:
    s = str(value or "").strip().lower().replace("ё", "е").replace("×", "x")
    s = re.sub(r"(?<=[a-z0-9])е|е(?=[a-z0-9])", "e", s)
    s = re.sub(r"\bglonass\b", "глонасс", s)
    return " ".join(s.split())


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [_coerce_text(x) for x in value]
        parts = [x for x in parts if x]
        return ", ".join(parts)
    if isinstance(value, dict):
        for key in ("value", "title", "name", "label"):
            if key in value:
                return _coerce_text(value.get(key))
        return ""
    return str(value).strip()


def _dictionary_items(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = doc.get("items")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and str(x.get("value") or "").strip()]


def _normalized_aliases(doc: Dict[str, Any]) -> Dict[str, str]:
    raw = doc.get("aliases")
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in raw.items():
        nk = normalize_value_key(key)
        vv = str(value or "").strip()
        if nk and vv:
            out[nk] = vv
    return out


def _source_reference(doc: Dict[str, Any], provider: str) -> Dict[str, Any]:
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    ref = meta.get("source_reference") if isinstance(meta.get("source_reference"), dict) else {}
    prow = ref.get(provider) if isinstance(ref.get(provider), dict) else {}
    return prow


def _export_map(doc: Dict[str, Any], provider: str) -> Dict[str, str]:
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    raw = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
    row = raw.get(provider) if isinstance(raw.get(provider), dict) else {}
    out: Dict[str, str] = {}
    for key, value in row.items():
        nk = normalize_value_key(key)
        vv = str(value or "").strip()
        if nk and vv:
            out[nk] = vv
    return out


def _set_export_map(doc: Dict[str, Any], provider: str, canonical_value: str, source_value: str) -> bool:
    canonical_key = normalize_value_key(canonical_value)
    source_text = str(source_value or "").strip()
    if not canonical_key or not source_text:
        return False
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    export_map = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
    provider_map = export_map.get(provider) if isinstance(export_map.get(provider), dict) else {}
    if provider_map.get(canonical_key) == source_text:
        return False
    provider_map[canonical_key] = source_text
    export_map[provider] = provider_map
    meta["export_map"] = export_map
    doc["meta"] = meta
    return True


def _split_composite_value(value: str) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s*(?:,|;|\band\b|\bи\b)\s*", raw, flags=re.IGNORECASE)
    cleaned: List[str] = []
    seen: set[str] = set()
    for part in parts:
        text = str(part or "").strip(" .")
        key = normalize_value_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned if len(cleaned) >= 2 else []


def _resolve_single_allowed_value(
    *,
    value: str,
    provider_map: Dict[str, str],
    allowed_values: List[str],
    aliases: Dict[str, str],
) -> Optional[str]:
    key = normalize_value_key(value)
    if not key:
        return None
    if key in provider_map:
        return provider_map[key]
    allowed_by_key = {
        normalize_value_key(candidate): str(candidate or "").strip()
        for candidate in allowed_values
        if normalize_value_key(candidate)
    }
    if key in allowed_by_key:
        return allowed_by_key[key]
    canonical = aliases.get(key, value)
    canonical_key = normalize_value_key(canonical)
    if canonical_key in provider_map:
        return provider_map[canonical_key]
    if canonical_key in allowed_by_key:
        return allowed_by_key[canonical_key]
    semantic = _resolve_semantic_allowed_value(value, allowed_values)
    if semantic:
        return semantic
    return None


def _resolve_semantic_allowed_value(value: str, allowed_values: List[str]) -> Optional[str]:
    key = normalize_value_key(value)
    if not key or not allowed_values:
        return None
    allowed_by_key = {
        normalize_value_key(candidate): str(candidate or "").strip()
        for candidate in allowed_values
        if normalize_value_key(candidate)
    }

    compact = re.sub(r"[\s\\/_-]+", "", key)
    if compact in {"esim+esim", "dualеsim", "dualesim"}:
        for candidate_key in ("dual esim", "2 nano sim+2 esim", "2 nano-sim/+esim"):
            if candidate_key in allowed_by_key:
                return allowed_by_key[candidate_key]

    screen_match = re.search(r"(\d{3,4})\s*[xх]\s*(\d{3,4})", key)
    if screen_match:
        normalized_resolution = f"{screen_match.group(1)}x{screen_match.group(2)}"
        if normalized_resolution in allowed_by_key:
            return allowed_by_key[normalized_resolution]

    if "4k" in key:
        for allowed_key, allowed_text in allowed_by_key.items():
            if "3840x2160" in allowed_key or "3840 2160" in allowed_key:
                return allowed_text

    if "мп" in key or "mp" in key:
        numbers = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[,.]\d+)?", key)]
        if numbers:
            primary = max(numbers)
            for allowed_key, allowed_text in allowed_by_key.items():
                bounds = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[,.]\d+)?", allowed_key)]
                if len(bounds) >= 2 and ("мп" in allowed_key or "mp" in allowed_key) and min(bounds[:2]) <= primary <= max(bounds[:2]):
                    return allowed_text
                if len(bounds) == 1 and abs(bounds[0] - primary) < 0.0001:
                    return allowed_text

    return None


def canonicalize_dictionary_value(dict_id: str, raw_value: Any) -> str:
    did = str(dict_id or "").strip()
    value = _coerce_text(raw_value)
    if not did or not value:
        return value

    doc = load_dict(did)
    items = _dictionary_items(doc)
    aliases = _normalized_aliases(doc)
    value_key = normalize_value_key(value)
    if not value_key:
        return value

    canonical = aliases.get(value_key, "")
    if not canonical:
        for item in items:
            item_value = str(item.get("value") or "").strip()
            if normalize_value_key(item_value) == value_key:
                canonical = item_value
                break
    if not canonical:
        # Competitor cards often append explanatory text to a controlled value:
        # "IP68 допускается..." should normalize to the dictionary value "IP68".
        matching_items: List[str] = []
        padded_value_key = f" {value_key} "
        for item in items:
            item_value = str(item.get("value") or "").strip()
            item_key = normalize_value_key(item_value)
            if not item_key or len(item_key) < 3:
                continue
            if padded_value_key.startswith(f" {item_key} ") or f" {item_key} " in padded_value_key:
                matching_items.append(item_value)
        if matching_items:
            canonical = sorted(matching_items, key=len, reverse=True)[0]
    if not canonical:
        canonical = value

    changed = False
    canonical_key = normalize_value_key(canonical)
    if canonical_key and canonical_key != value_key:
        raw_aliases = doc.get("aliases") if isinstance(doc.get("aliases"), dict) else {}
        if raw_aliases.get(value_key) != canonical:
            raw_aliases[value_key] = canonical
            doc["aliases"] = raw_aliases
            changed = True

    # If the competitor value exactly matches an allowed marketplace value,
    # remember that equivalence for future export.
    for provider in ("yandex_market", "ozon"):
        ref = _source_reference(doc, provider)
        allowed = ref.get("allowed_values") if isinstance(ref.get("allowed_values"), list) else []
        for candidate in allowed:
            source_value = str(candidate or "").strip()
            if not source_value:
                continue
            if normalize_value_key(source_value) == value_key or normalize_value_key(source_value) == canonical_key:
                if _set_export_map(doc, provider, canonical, source_value):
                    changed = True
                break

    if changed:
        save_dict(doc)
    return canonical


def provider_export_value_details(dict_id: Optional[str], provider: str, canonical_value: Any) -> Dict[str, Any]:
    value = _coerce_text(canonical_value)
    did = str(dict_id or "").strip()
    if not did or not value:
        return {
            "value": value,
            "mapped": True,
            "reason": "free_text" if value else "empty",
        }

    doc = load_dict(did)
    key = normalize_value_key(value)
    if not key:
        return {"value": value, "mapped": False, "reason": "empty"}

    provider_map = _export_map(doc, provider)
    if key in provider_map:
        return {"value": provider_map[key], "mapped": True, "reason": "export_map"}

    ref = _source_reference(doc, provider)
    allowed = ref.get("allowed_values") if isinstance(ref.get("allowed_values"), list) else []
    for candidate in allowed:
        source_value = str(candidate or "").strip()
        if source_value and normalize_value_key(source_value) == key:
            return {"value": source_value, "mapped": True, "reason": "allowed_exact"}

    aliases = _normalized_aliases(doc)
    canonical = aliases.get(key, value)
    canonical_key = normalize_value_key(canonical)
    if canonical_key in provider_map:
        return {"value": provider_map[canonical_key], "mapped": True, "reason": "alias_export_map"}
    for candidate in allowed:
        source_value = str(candidate or "").strip()
        if source_value and normalize_value_key(source_value) == canonical_key:
            return {"value": source_value, "mapped": True, "reason": "alias_allowed_exact"}

    if allowed:
        semantic_value = _resolve_semantic_allowed_value(value, allowed)
        if semantic_value:
            return {"value": semantic_value, "mapped": True, "reason": "semantic_allowed"}
        composite_parts = _split_composite_value(value)
        if composite_parts:
            mapped_parts: List[str] = []
            seen_parts: set[str] = set()
            for part in composite_parts:
                resolved = _resolve_single_allowed_value(
                    value=part,
                    provider_map=provider_map,
                    allowed_values=allowed,
                    aliases=aliases,
                )
                resolved_key = normalize_value_key(resolved)
                if not resolved or not resolved_key:
                    mapped_parts = []
                    break
                if resolved_key not in seen_parts:
                    seen_parts.add(resolved_key)
                    mapped_parts.append(resolved)
            if mapped_parts:
                return {
                    "value": ", ".join(mapped_parts),
                    "values": mapped_parts,
                    "mapped": True,
                    "reason": "composite_allowed",
                }

    # Providers with an allowed-value list are controlled dictionaries. Falling
    # back to PIM canonical value would make the UI/export look ready while the
    # marketplace value is actually unmapped.
    if allowed:
        return {"value": "", "mapped": False, "reason": "value_missing"}

    return {"value": canonical, "mapped": True, "reason": "free_text"}


def provider_export_value(dict_id: Optional[str], provider: str, canonical_value: Any) -> str:
    details = provider_export_value_details(dict_id, provider, canonical_value)
    return str(details.get("value") or "").strip() or _coerce_text(canonical_value)


def provider_import_value(dict_id: Optional[str], provider: str, source_value: Any) -> str:
    value = _coerce_text(source_value)
    did = str(dict_id or "").strip()
    if not did or not value:
        return value

    doc = load_dict(did)
    raw_value = str(value or "").strip()
    value_key = normalize_value_key(raw_value)
    if not value_key:
        return raw_value

    aliases = _normalized_aliases(doc)
    provider_map = _export_map(doc, provider)
    for canonical_key, provider_value in provider_map.items():
        if normalize_value_key(provider_value) == value_key:
            for item in _dictionary_items(doc):
                item_value = str(item.get("value") or "").strip()
                if normalize_value_key(item_value) == canonical_key:
                    return item_value
            return aliases.get(canonical_key, raw_value) or raw_value

    ref = _source_reference(doc, provider)
    allowed = ref.get("allowed_values") if isinstance(ref.get("allowed_values"), list) else []
    for candidate in allowed:
        source_text = str(candidate or "").strip()
        if source_text and normalize_value_key(source_text) == value_key:
            if _set_export_map(doc, provider, raw_value, source_text):
                save_dict(doc)
            return aliases.get(value_key, raw_value) or raw_value

    canonical = aliases.get(value_key, "")
    if canonical:
        return canonical

    for item in _dictionary_items(doc):
        item_value = str(item.get("value") or "").strip()
        if normalize_value_key(item_value) == value_key:
            return item_value

    return raw_value
