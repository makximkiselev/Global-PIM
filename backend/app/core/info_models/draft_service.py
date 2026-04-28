from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

from app.core.products.service import query_products_full
from app.core.json_store import DATA_DIR, read_doc
from app.storage.json_store import load_templates_db, new_id, save_templates_db
from app.storage.relational_pim_store import load_category_mappings


MARKETPLACES_DIR = DATA_DIR / "marketplaces"
YANDEX_CATEGORY_PARAMS_PATH = MARKETPLACES_DIR / "yandex_market" / "category_parameters.json"
OZON_CATEGORY_ATTRS_PATH = MARKETPLACES_DIR / "ozon" / "category_attributes.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slugify(value: str) -> str:
    table = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    out: List[str] = []
    prev_sep = False
    for ch in _text(value).lower():
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
            prev_sep = False
        elif ch in table:
            out.append(table[ch])
            prev_sep = False
        elif not prev_sep:
            out.append("_")
            prev_sep = True
    return "".join(out).strip("_") or "field"


def _infer_type(values: Iterable[str]) -> str:
    clean = [_text(value) for value in values if _text(value)]
    if not clean:
        return "text"
    numeric = 0
    for value in clean:
        normalized = value.replace(",", ".").replace(" ", "")
        if normalized.replace(".", "", 1).isdigit():
            numeric += 1
    if numeric == len(clean):
        return "number"
    if len(set(clean)) <= 24:
        return "select"
    return "text"


def _infer_type_from_kind(kind_raw: str, values: Iterable[str]) -> str:
    kind = _text(kind_raw).lower()
    if any(token in kind for token in ("bool", "boolean", "да/нет")):
        return "bool"
    if any(token in kind for token in ("int", "integer", "numeric", "number", "decimal", "float", "число")):
        return "number"
    if any(token in kind for token in ("enum", "select", "список", "выбор")):
        return "select"
    return _infer_type(values)


def _extract_text_list(values: Any) -> List[str]:
    out: List[str] = []
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str):
                text = _text(value)
                if text:
                    out.append(text)
            elif isinstance(value, (int, float)):
                out.append(str(value))
            elif isinstance(value, dict):
                for key in ("value", "name", "title", "label"):
                    text = _text(value.get(key))
                    if text:
                        out.append(text)
                        break
    return out


def _normalize_provider_category_lookup_id(provider: str, provider_category_id: str) -> str:
    pid = _text(provider_category_id)
    if provider == "ozon" and pid.startswith("type:"):
        parts = pid.split(":")
        if len(parts) >= 3:
            return _text(parts[1])
    return pid


def _feature_items(product: Dict[str, Any]) -> Iterable[Tuple[str, str]]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    features = content.get("features") if isinstance(content.get("features"), list) else []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        name = _text(feature.get("name") or feature.get("code"))
        value = _text(feature.get("value"))
        if name:
            yield name, value


def _product_candidates(category_id: str) -> List[Dict[str, Any]]:
    products = [p for p in query_products_full() if isinstance(p, dict) and _text(p.get("category_id")) == category_id]
    by_code: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for product in products:
        for name, value in _feature_items(product):
            code = _slugify(name)
            row = by_code.get(code)
            if not row:
                row = {
                    "id": new_id(),
                    "name": name,
                    "code": code,
                    "group": "Характеристики",
                    "required": False,
                    "examples": [],
                    "sources": [],
                    "_count": 0,
                }
                by_code[code] = row
            row["_count"] += 1
            if value and value not in row["examples"]:
                row["examples"].append(value)
            if not row["sources"]:
                row["sources"].append(
                    {
                        "kind": "product",
                        "provider": "existing_products",
                        "source_name": "Товары категории",
                        "field_name": code,
                        "examples": [],
                        "count": 0,
                    }
                )
            source = row["sources"][0]
            source["count"] = int(source.get("count") or 0) + 1
            if value and value not in source["examples"]:
                source["examples"].append(value)

    out: List[Dict[str, Any]] = []
    product_count = max(len(products), 1)
    for row in by_code.values():
        examples = row.get("examples") if isinstance(row.get("examples"), list) else []
        row["type"] = _infer_type(examples)
        row["confidence"] = min(0.95, round(0.45 + (float(row.get("_count") or 0) / product_count) * 0.45, 2))
        row["status"] = "accepted" if row["confidence"] >= 0.65 else "needs_review"
        row.pop("_count", None)
        out.append(row)
    return out


def _load_yandex_params(provider_category_id: str) -> List[Dict[str, Any]]:
    if not provider_category_id:
        return []
    doc = read_doc(YANDEX_CATEGORY_PARAMS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    row = items.get(str(provider_category_id)) if isinstance(items, dict) else None
    if not isinstance(row, dict):
        return []
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    result = raw.get("result") if isinstance(raw, dict) else {}
    params = result.get("parameters") if isinstance(result, dict) else []
    out: List[Dict[str, Any]] = []
    if not isinstance(params, list):
        return out
    for param in params:
        if not isinstance(param, dict):
            continue
        pid = _text(param.get("id"))
        name = _text(param.get("name"))
        if not pid and not name:
            continue
        values: List[str] = []
        for key in ("values", "options", "enumValues", "suggestedValues"):
            values = _extract_text_list(param.get(key))
            if values:
                break
        kind = _text(param.get("type"))
        if bool(param.get("multivalue") or False):
            kind = f"{kind} multivalue".strip()
        out.append(
            {
                "id": pid or name,
                "name": name or pid,
                "required": bool(param.get("required") or False),
                "kind": kind,
                "values": values[:120],
                "provider": "yandex_market",
                "source_name": "Я.Маркет",
            }
        )
    return out


def _load_ozon_params(provider_category_id: str) -> List[Dict[str, Any]]:
    lookup_id = _normalize_provider_category_lookup_id("ozon", provider_category_id)
    if not lookup_id:
        return []
    doc = read_doc(OZON_CATEGORY_ATTRS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    row = items.get(str(lookup_id)) if isinstance(items, dict) else None
    if not isinstance(row, dict):
        return []
    attrs = row.get("attributes") if isinstance(row.get("attributes"), list) else []
    out: List[Dict[str, Any]] = []
    for param in attrs:
        if not isinstance(param, dict):
            continue
        pid = _text(param.get("id"))
        name = _text(param.get("name") or param.get("attribute_name"))
        if not pid and not name:
            continue
        values: List[str] = []
        for key in ("values", "dictionary", "options", "available_values"):
            values = _extract_text_list(param.get(key))
            if values:
                break
        out.append(
            {
                "id": pid or name,
                "name": name or pid,
                "required": bool(param.get("is_required") or param.get("required") or False),
                "kind": _text(param.get("type") or param.get("value_type")),
                "values": values[:120],
                "provider": "ozon",
                "source_name": "Ozon",
            }
        )
    return out


def _merge_candidate(base: Dict[str, Any], next_item: Dict[str, Any]) -> Dict[str, Any]:
    base["required"] = bool(base.get("required") or next_item.get("required"))
    base["confidence"] = max(float(base.get("confidence") or 0), float(next_item.get("confidence") or 0))
    if _text(next_item.get("type")) == "select" and _text(base.get("type")) not in {"select", "json"}:
        base["type"] = "select"
    for value in next_item.get("examples") if isinstance(next_item.get("examples"), list) else []:
        if value and value not in base.setdefault("examples", []):
            base["examples"].append(value)
    for source in next_item.get("sources") if isinstance(next_item.get("sources"), list) else []:
        if isinstance(source, dict):
            base.setdefault("sources", []).append(source)
    if base.get("required"):
        base["status"] = "accepted"
    return base


def _marketplace_candidates(category_id: str) -> List[Dict[str, Any]]:
    mappings = load_category_mappings()
    mapping = mappings.get(category_id) if isinstance(mappings, dict) else None
    if not isinstance(mapping, dict):
        return []
    provider_params: List[Dict[str, Any]] = []
    yandex_category_id = _text(mapping.get("yandex_market"))
    if yandex_category_id:
        provider_params.extend(_load_yandex_params(yandex_category_id))
    ozon_category_id = _text(mapping.get("ozon"))
    if ozon_category_id:
        provider_params.extend(_load_ozon_params(ozon_category_id))

    by_code: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for param in provider_params:
        name = _text(param.get("name"))
        if not name:
            continue
        code = _slugify(name)
        values = param.get("values") if isinstance(param.get("values"), list) else []
        provider = _text(param.get("provider"))
        candidate = {
            "id": new_id(),
            "name": name,
            "code": code,
            "group": "Требования площадок",
            "required": bool(param.get("required") or False),
            "examples": values[:8],
            "type": _infer_type_from_kind(_text(param.get("kind")), values),
            "confidence": 0.9 if bool(param.get("required") or False) else 0.72,
            "status": "accepted" if bool(param.get("required") or False) else "needs_review",
            "sources": [
                {
                    "kind": "marketplace",
                    "provider": provider,
                    "source_name": _text(param.get("source_name")) or provider,
                    "field_name": _text(param.get("id")) or code,
                    "examples": values[:8],
                    "count": 1,
                }
            ],
        }
        existing = by_code.get(code)
        by_code[code] = _merge_candidate(existing, candidate) if existing else candidate
    return list(by_code.values())


def _template_for_category(db: Dict[str, Any], category_id: str) -> Tuple[str, Dict[str, Any] | None]:
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    category_to_templates = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    ids = category_to_templates.get(category_id) if isinstance(category_to_templates.get(category_id), list) else []
    template_id = _text((ids or [""])[0])
    template = templates.get(template_id) if template_id else None
    return template_id, template if isinstance(template, dict) else None


def _ensure_template(db: Dict[str, Any], category_id: str, name: str) -> Dict[str, Any]:
    template_id, template = _template_for_category(db, category_id)
    if template:
        return template
    template_id = new_id()
    template = {
        "id": template_id,
        "category_id": category_id,
        "name": name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "meta": {"sources": {}},
    }
    db.setdefault("templates", {})[template_id] = template
    db.setdefault("attributes", {})[template_id] = []
    db.setdefault("category_to_template", {})[category_id] = template_id
    db.setdefault("category_to_templates", {}).setdefault(category_id, [])
    if template_id not in db["category_to_templates"][category_id]:
        db["category_to_templates"][category_id].append(template_id)
    return template


def _info_model_meta(template: Dict[str, Any]) -> Dict[str, Any]:
    meta = template.get("meta") if isinstance(template.get("meta"), dict) else {}
    info_model = meta.get("info_model") if isinstance(meta.get("info_model"), dict) else {}
    meta["info_model"] = info_model
    template["meta"] = meta
    return info_model


def create_draft_from_sources(category_id: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cid = _text(category_id)
    if not cid:
        raise ValueError("CATEGORY_REQUIRED")
    selected_sources = payload.get("sources") if isinstance(payload, dict) and isinstance(payload.get("sources"), list) else ["products"]
    db = load_templates_db()
    template = _ensure_template(db, cid, f"Draft: {cid}")
    info_model = _info_model_meta(template)
    candidates: List[Dict[str, Any]] = []
    if "products" in selected_sources:
        candidates.extend(_product_candidates(cid))
    if "marketplaces" in selected_sources:
        existing_by_code = OrderedDict((str(item.get("code") or ""), item) for item in candidates if isinstance(item, dict))
        for candidate in _marketplace_candidates(cid):
            code = str(candidate.get("code") or "").strip()
            existing = existing_by_code.get(code)
            existing_by_code[code] = _merge_candidate(existing, candidate) if existing else candidate
        candidates = list(existing_by_code.values())
    info_model.update(
        {
            "status": "draft",
            "draft_sources": selected_sources,
            "draft_generated_at": now_iso(),
            "approved_at": None,
            "candidates": candidates,
        }
    )
    template["updated_at"] = now_iso()
    db["templates"][template["id"]] = template
    save_templates_db(db)
    return {"ok": True, "template": template, "info_model": info_model, "candidates": candidates}


def update_draft_candidate(template_id: str, candidate_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    db = load_templates_db()
    template = (db.get("templates") or {}).get(template_id)
    if not isinstance(template, dict):
        raise ValueError("TEMPLATE_NOT_FOUND")
    info_model = _info_model_meta(template)
    candidates = info_model.get("candidates") if isinstance(info_model.get("candidates"), list) else []
    for candidate in candidates:
        if isinstance(candidate, dict) and _text(candidate.get("id")) == candidate_id:
            for key in ("name", "code", "type", "group", "required", "status"):
                if key in patch:
                    candidate[key] = patch[key]
            template["updated_at"] = now_iso()
            db["templates"][template_id] = template
            save_templates_db(db)
            return {"ok": True, "candidate": candidate, "info_model": info_model}
    raise ValueError("CANDIDATE_NOT_FOUND")


def approve_draft(template_id: str) -> Dict[str, Any]:
    db = load_templates_db()
    template = (db.get("templates") or {}).get(template_id)
    if not isinstance(template, dict):
        raise ValueError("TEMPLATE_NOT_FOUND")
    info_model = _info_model_meta(template)
    candidates = info_model.get("candidates") if isinstance(info_model.get("candidates"), list) else []
    attrs: List[Dict[str, Any]] = []
    for position, candidate in enumerate(c for c in candidates if isinstance(c, dict) and c.get("status") == "accepted"):
        attrs.append(
            {
                "id": new_id(),
                "name": _text(candidate.get("name")),
                "code": _text(candidate.get("code")) or _slugify(_text(candidate.get("name"))),
                "type": _text(candidate.get("type")) or "text",
                "required": bool(candidate.get("required")),
                "scope": "feature",
                "position": position,
                "options": {
                    "param_group": _text(candidate.get("group")) or "Характеристики",
                    "source_candidates": [_text(candidate.get("id"))],
                },
            }
        )
    db.setdefault("attributes", {})[template_id] = attrs
    info_model["status"] = "approved"
    info_model["approved_at"] = now_iso()
    template["updated_at"] = now_iso()
    db["templates"][template_id] = template
    save_templates_db(db)
    return {"ok": True, "template": template, "info_model": info_model, "attributes": attrs}
