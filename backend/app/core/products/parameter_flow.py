from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.core.value_mapping import provider_export_value
from app.storage.relational_pim_store import (
    load_attribute_mapping_doc,
    load_attribute_value_refs_doc,
    load_catalog_nodes,
)


PROVIDER_LABELS: Dict[str, str] = {
    "yandex_market": "Я.Маркет",
    "ozon": "Ozon",
    "restore": "re-store",
    "store77": "Store77",
}

MARKETPLACE_PROVIDERS: tuple[str, ...] = ("yandex_market", "ozon")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("ё", "е").split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join([part for part in (_text(item) for item in value) if part])
    if isinstance(value, dict):
        for key in ("value", "name", "title", "label", "raw_value", "resolved_value", "canonical_value"):
            if key in value:
                resolved = _text(value.get(key))
                if resolved:
                    return resolved
        return ""
    return str(value).strip()


def _provider_bindings(raw: Any) -> List[Dict[str, Any]]:
    cur = raw if isinstance(raw, dict) else {}
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add(item: Any) -> None:
        candidate = item if isinstance(item, dict) else {}
        payload = {
            "id": _text(candidate.get("id")),
            "name": _text(candidate.get("name")),
            "kind": _text(candidate.get("kind")),
            "values": list(candidate.get("values") or []) if isinstance(candidate.get("values"), list) else [],
            "required": bool(candidate.get("required") or False),
            "export": bool(candidate.get("export") or False),
        }
        if not payload["id"] and not payload["name"]:
            return
        key = payload["id"] or f"name:{payload['name'].lower()}"
        if key in seen:
            return
        seen.add(key)
        out.append(payload)

    _add(cur)
    for item in cur.get("bindings") if isinstance(cur.get("bindings"), list) else []:
        _add(item)
    return out


def _parent_map(nodes: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for node in nodes:
        node_id = str((node or {}).get("id") or "").strip()
        parent_id = str((node or {}).get("parent_id") or "").strip()
        if node_id and parent_id:
            out[node_id] = parent_id
    return out


def _effective_attr_rows(category_id: str, rows_by_category: Dict[str, List[Dict[str, Any]]], parent_by_id: Dict[str, str]) -> List[Dict[str, Any]]:
    current = str(category_id or "").strip()
    seen: Set[str] = set()
    while current and current not in seen:
        seen.add(current)
        rows = rows_by_category.get(current) or []
        if rows:
            return rows
        current = parent_by_id.get(current, "")
    return []


def _effective_value_ref(category_id: str, refs_by_category: Dict[str, Dict[str, Any]], parent_by_id: Dict[str, str]) -> Dict[str, Any]:
    current = str(category_id or "").strip()
    seen: Set[str] = set()
    while current and current not in seen:
        seen.add(current)
        row = refs_by_category.get(current)
        if isinstance(row, dict):
            return row
        current = parent_by_id.get(current, "")
    return {}


def _load_attr_rows_by_category() -> Dict[str, List[Dict[str, Any]]]:
    doc = load_attribute_mapping_doc()
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for category_id, payload in items.items():
        rows = payload.get("rows") if isinstance(payload, dict) else []
        if isinstance(rows, list) and rows:
            out[str(category_id)] = [dict(row) for row in rows if isinstance(row, dict)]
    return out


def _load_value_refs_by_category() -> Dict[str, Dict[str, Any]]:
    doc = load_attribute_value_refs_doc()
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return {}
    return {str(category_id): dict(payload) for category_id, payload in items.items() if isinstance(payload, dict)}


def _dict_id_for_catalog_name(category_id: str, catalog_name: str, refs_by_category: Dict[str, Dict[str, Any]], parent_by_id: Dict[str, str]) -> str:
    ref = _effective_value_ref(category_id, refs_by_category, parent_by_id)
    params = ref.get("catalog_params") if isinstance(ref.get("catalog_params"), dict) else {}
    target = _norm(catalog_name)
    for payload in params.values():
        if not isinstance(payload, dict):
            continue
        if _norm(payload.get("catalog_name")) == target:
            return str(payload.get("dict_id") or "").strip()
    return ""


def _features(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    raw = content.get("features") if isinstance(content.get("features"), list) else []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _feature_key(feature: Dict[str, Any]) -> str:
    return _norm(feature.get("code") or feature.get("name"))


def _feature_value(feature: Dict[str, Any]) -> str:
    return _text(feature.get("value") if "value" in feature else feature.get("values"))


def _feature_source_entries(feature: Dict[str, Any]) -> List[Dict[str, Any]]:
    source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
    entries: List[Dict[str, Any]] = []
    for group_key, group_payload in source_values.items():
        if not isinstance(group_payload, dict):
            continue
        for source_id, payload in group_payload.items():
            if not isinstance(payload, dict):
                continue
            raw_value = _text(payload.get("raw_value") or payload.get("value"))
            resolved_value = _text(payload.get("resolved_value") or payload.get("canonical_value") or raw_value)
            if not raw_value and not resolved_value:
                continue
            entries.append(
                {
                    "group": str(group_key or "").strip(),
                    "source_id": str(source_id or "").strip(),
                    "source_label": PROVIDER_LABELS.get(str(source_id or "").strip(), str(source_id or "").strip()),
                    "raw_value": raw_value,
                    "resolved_value": resolved_value,
                    "canonical_value": _text(payload.get("canonical_value")),
                }
            )
    return entries


def _marketplace_outputs(
    *,
    category_id: str,
    row: Optional[Dict[str, Any]],
    catalog_name: str,
    canonical_value: str,
    refs_by_category: Dict[str, Dict[str, Any]],
    parent_by_id: Dict[str, str],
) -> List[Dict[str, Any]]:
    pmap = row.get("provider_map") if isinstance(row, dict) and isinstance(row.get("provider_map"), dict) else {}
    dict_id = _dict_id_for_catalog_name(category_id, catalog_name, refs_by_category, parent_by_id)
    outputs: List[Dict[str, Any]] = []
    for provider in MARKETPLACE_PROVIDERS:
        provider_row = pmap.get(provider) if isinstance(pmap.get(provider), dict) else {}
        bindings = _provider_bindings(provider_row)
        if not bindings:
            outputs.append(
                {
                    "provider": provider,
                    "provider_label": PROVIDER_LABELS.get(provider, provider),
                    "target_id": "",
                    "target_name": "",
                    "export": False,
                    "dict_id": dict_id,
                    "output_value": "",
                    "status": "not_mapped",
                    "label": "поле не сопоставлено",
                }
            )
            continue
        for index, binding in enumerate(bindings):
            target_id = str(binding.get("id") or "").strip()
            target_name = str(binding.get("name") or "").strip()
            export_enabled = bool(binding.get("export")) if binding else False
            output_value = provider_export_value(dict_id, provider, canonical_value) if canonical_value else ""
            if not export_enabled:
                status = "not_exported"
                label = "не выгружается"
            elif not canonical_value:
                status = "empty"
                label = "нет значения"
            elif not output_value:
                status = "value_missing"
                label = "значение не сопоставлено"
            else:
                status = "ready"
                label = "готово"
            outputs.append(
                {
                    "provider": provider,
                    "provider_label": PROVIDER_LABELS.get(provider, provider),
                    "target_id": target_id,
                    "target_name": target_name,
                    "export": export_enabled,
                    "dict_id": dict_id,
                    "output_value": output_value,
                    "status": status,
                    "label": label,
                    "binding_index": index,
                    "primary": index == 0,
                }
            )
    return outputs


def _service_rows(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    sku_gt = str(product.get("sku_gt") or "").strip()
    title = str(product.get("title") or "").strip()
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    description = str(content.get("description") or "").strip()
    images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
    return [
        {
            "key": "service:sku_gt",
            "kind": "service",
            "code": "sku_gt",
            "name": "SKU GT",
            "value": sku_gt,
            "sources": [{"source_id": "pim", "source_label": "SmartPim", "resolved_value": sku_gt}] if sku_gt else [],
            "marketplaces": [
                {
                    "provider": "yandex_market",
                    "provider_label": "Я.Маркет",
                    "target_id": "offerId",
                    "target_name": "offerId",
                    "export": True,
                    "output_value": sku_gt,
                    "status": "ready" if sku_gt else "empty",
                    "label": "готово" if sku_gt else "нет значения",
                },
                {
                    "provider": "ozon",
                    "provider_label": "Ozon",
                    "target_id": "offer_id",
                    "target_name": "offer_id",
                    "export": True,
                    "output_value": sku_gt,
                    "status": "ready" if sku_gt else "empty",
                    "label": "готово" if sku_gt else "нет значения",
                },
            ],
        },
        {
            "key": "service:title",
            "kind": "service",
            "code": "title",
            "name": "Название товара",
            "value": title,
            "sources": [{"source_id": "pim", "source_label": "SmartPim", "resolved_value": title}] if title else [],
            "marketplaces": [],
        },
        {
            "key": "service:description",
            "kind": "service",
            "code": "description",
            "name": "Описание",
            "value": description,
            "sources": [],
            "marketplaces": [],
        },
        {
            "key": "service:media_images",
            "kind": "service",
            "code": "media_images",
            "name": "Медиа",
            "value": f"{len(images)} фото" if images else "",
            "sources": [],
            "marketplaces": [],
        },
    ]


def build_product_parameter_flow(product: Dict[str, Any]) -> Dict[str, Any]:
    category_id = str(product.get("category_id") or "").strip()
    nodes = load_catalog_nodes()
    parent_by_id = _parent_map(nodes)
    rows_by_category = _load_attr_rows_by_category()
    refs_by_category = _load_value_refs_by_category()
    rows = _effective_attr_rows(category_id, rows_by_category, parent_by_id)
    row_by_key: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _norm(row.get("catalog_name"))
        if key and key not in row_by_key:
            row_by_key[key] = row

    items: List[Dict[str, Any]] = []
    ready = 0
    attention = 0
    empty = 0
    source_count = 0
    for feature in _features(product):
        name = str(feature.get("name") or feature.get("code") or "").strip()
        if not name:
            continue
        key = _feature_key(feature)
        value = _feature_value(feature)
        row = row_by_key.get(_norm(name)) or row_by_key.get(_norm(feature.get("code")))
        sources = _feature_source_entries(feature)
        marketplaces = _marketplace_outputs(
            category_id=category_id,
            row=row,
            catalog_name=str((row or {}).get("catalog_name") or name),
            canonical_value=value,
            refs_by_category=refs_by_category,
            parent_by_id=parent_by_id,
        )
        statuses = {str(item.get("status") or "") for item in marketplaces}
        if not value:
            row_status = "empty"
            empty += 1
        elif "not_mapped" in statuses or "value_missing" in statuses:
            row_status = "attention"
            attention += 1
        else:
            row_status = "ready"
            ready += 1
        source_count += len(sources)
        items.append(
            {
                "key": key or name,
                "kind": "feature",
                "code": str(feature.get("code") or "").strip(),
                "name": name,
                "value": value,
                "required": bool((row or {}).get("required") or feature.get("required")),
                "status": row_status,
                "sources": sources,
                "marketplaces": marketplaces,
            }
        )

    service_rows = _service_rows(product)
    return {
        "ok": True,
        "product_id": str(product.get("id") or "").strip(),
        "category_id": category_id,
        "summary": {
            "features_total": len(items),
            "features_ready": ready,
            "features_attention": attention,
            "features_empty": empty,
            "source_values": source_count,
            "service_rows": len(service_rows),
        },
        "service_rows": service_rows,
        "items": items,
    }
