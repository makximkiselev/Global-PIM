from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.storage.json_store import load_dict, save_dict


def normalize_value_key(value: Any) -> str:
    s = str(value or "").strip().lower().replace("ё", "е")
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


def provider_export_value(dict_id: Optional[str], provider: str, canonical_value: Any) -> str:
    value = _coerce_text(canonical_value)
    did = str(dict_id or "").strip()
    if not did or not value:
        return value

    doc = load_dict(did)
    key = normalize_value_key(value)
    if not key:
        return value

    provider_map = _export_map(doc, provider)
    if key in provider_map:
        return provider_map[key]

    ref = _source_reference(doc, provider)
    allowed = ref.get("allowed_values") if isinstance(ref.get("allowed_values"), list) else []
    for candidate in allowed:
        source_value = str(candidate or "").strip()
        if not source_value:
            continue
        if normalize_value_key(source_value) == key:
            return source_value

    aliases = _normalized_aliases(doc)
    canonical = aliases.get(key, value)
    canonical_key = normalize_value_key(canonical)
    if canonical_key in provider_map:
        return provider_map[canonical_key]
    for candidate in allowed:
        source_value = str(candidate or "").strip()
        if not source_value:
            continue
        if normalize_value_key(source_value) == canonical_key:
            return source_value

    return canonical


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
