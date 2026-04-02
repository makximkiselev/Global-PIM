# backend/app/storage/json_store.py
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from app.core.json_store import read_doc as core_read_json, write_doc as core_write_json

BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/
DATA_DIR = BACKEND_DIR / "data"

TEMPLATES_FILE = DATA_DIR / "templates.json"


# =========================
# Templates store
# =========================

DEFAULT_TEMPLATES: Dict[str, Any] = {
    "version": 2,
    # template_id -> {id, name, category_id, updated_at, created_at}
    "templates": {},
    # template_id -> [ {id, name, code, type, required, scope, options, position} ]
    "attributes": {},
    # legacy: category_id -> template_id (первый/основной)
    "category_to_template": {},
    # ✅ новый формат: category_id -> [template_id, ...]
    "category_to_templates": {},
}


def _clone_default(default: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(default))


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = core_read_json(path, default=_clone_default(default))
        return data if isinstance(data, dict) else _clone_default(default)
    except Exception:
        return _clone_default(default)


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    core_write_json(path, data)


def _ensure_type(db: Dict[str, Any], key: str, sample: Any) -> None:
    if key not in db or not isinstance(db[key], type(sample)):
        db[key] = _clone_default({key: sample})[key]


def _dedupe_list_str(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen = set()
    for x in items:
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _migrate_templates_db(db: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ Миграции и нормализация структуры templates.json

    Поддерживаем:
    - legacy: category_to_template (1 шаблон на категорию)
    - new: category_to_templates (много шаблонов на категорию)
    """
    if not isinstance(db, dict):
        db = _clone_default(DEFAULT_TEMPLATES)

    _ensure_type(db, "version", 2)
    _ensure_type(db, "templates", {})
    _ensure_type(db, "attributes", {})
    _ensure_type(db, "category_to_template", {})
    _ensure_type(db, "category_to_templates", {})

    if not isinstance(db.get("templates"), dict):
        db["templates"] = {}
    if not isinstance(db.get("attributes"), dict):
        db["attributes"] = {}
    if not isinstance(db.get("category_to_template"), dict):
        db["category_to_template"] = {}
    if not isinstance(db.get("category_to_templates"), dict):
        db["category_to_templates"] = {}

    cat_to_tpl: Dict[str, Any] = db.get("category_to_template", {}) or {}
    cat_to_tpls: Dict[str, Any] = db.get("category_to_templates", {}) or {}

    normalized_cat_to_tpls: Dict[str, list[str]] = {}
    for cid, tids in cat_to_tpls.items():
        normalized_cat_to_tpls[str(cid)] = _dedupe_list_str(tids)
    cat_to_tpls = normalized_cat_to_tpls

    for cid, tid in cat_to_tpl.items():
        cid_s = str(cid).strip()
        tid_s = str(tid).strip() if tid is not None else ""
        if not cid_s or not tid_s:
            continue
        cat_to_tpls.setdefault(cid_s, [])
        if tid_s not in cat_to_tpls[cid_s]:
            cat_to_tpls[cid_s].insert(0, tid_s)

    db["category_to_templates"] = cat_to_tpls

    cat_to_tpl_out: Dict[str, str] = {}
    for cid, tids in cat_to_tpls.items():
        if tids:
            cat_to_tpl_out[str(cid)] = str(tids[0])
    db["category_to_template"] = cat_to_tpl_out

    templates: Dict[str, Any] = db.get("templates", {}) or {}
    fixed_templates: Dict[str, Any] = {}
    for k, v in templates.items():
        if not isinstance(v, dict):
            continue
        tid = str(v.get("id") or k).strip()
        if not tid:
            continue
        v["id"] = tid
        fixed_templates[tid] = v
    db["templates"] = fixed_templates

    attrs: Dict[str, Any] = db.get("attributes", {}) or {}
    fixed_attrs: Dict[str, Any] = {}
    for tid, arr in attrs.items():
        tid_s = str(tid).strip()
        if not tid_s:
            continue
        fixed_attrs[tid_s] = arr if isinstance(arr, list) else []
    db["attributes"] = fixed_attrs

    if not isinstance(db.get("version"), int):
        db["version"] = 2
    if db["version"] < 2:
        db["version"] = 2

    return db


def load_templates_db() -> Dict[str, Any]:
    db = _read_json(TEMPLATES_FILE, DEFAULT_TEMPLATES)
    db = _migrate_templates_db(db)

    for k, v in DEFAULT_TEMPLATES.items():
        if k not in db or not isinstance(db[k], type(v)):
            db[k] = _clone_default({k: v})[k]
    return db


def save_templates_db(db: Dict[str, Any]) -> None:
    db = _migrate_templates_db(db)
    _write_json_atomic(TEMPLATES_FILE, db)


def new_id() -> str:
    return str(uuid.uuid4())


def slugify_code(name: str) -> str:
    s = (name or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("_")
    code = "".join(out).strip("_")
    return code or "attr"


# =========================
# Competitor mapping store
# =========================

COMPETITOR_MAPPING_FILE = DATA_DIR / "competitor_mapping.json"

DEFAULT_COMPETITOR_MAPPING: Dict[str, Any] = {
    "version": 2,
    "categories": {
        # category_id -> {
        #   "priority_site": "restore"|"store77"|None,
        #   "links": {"restore": str, "store77": str},
        #   "mapping_by_site": {
        #       "restore": { "<our_attr_code>": "<competitor_field_name>" },
        #       "store77": { "<our_attr_code>": "<competitor_field_name>" }
        #   },
        #   "updated_at": iso
        # }
    },
    "templates": {
        # template_id -> {
        #   "priority_site": "restore"|"store77"|None,
        #   "links": {"restore": str, "store77": str},
        #   "mapping_by_site": {
        #       "restore": { "<our_attr_code>": "<competitor_field_name>" },
        #       "store77": { "<our_attr_code>": "<competitor_field_name>" }
        #   },
        #   "updated_at": iso
        # }
    }
}


def load_competitor_mapping_db() -> Dict[str, Any]:
    db = _read_json(COMPETITOR_MAPPING_FILE, DEFAULT_COMPETITOR_MAPPING)
    if not isinstance(db, dict):
        db = _clone_default(DEFAULT_COMPETITOR_MAPPING)

    if "version" not in db:
        db["version"] = 1  # legacy
    if "categories" not in db or not isinstance(db.get("categories"), dict):
        db["categories"] = {}
    if "templates" not in db or not isinstance(db.get("templates"), dict):
        db["templates"] = {}
    for cid, row in (db.get("categories") or {}).items():
        if not isinstance(row, dict):
            continue
        if "mapping_by_site" in row and isinstance(row.get("mapping_by_site"), dict):
            continue
        legacy = row.get("mapping")
        if isinstance(legacy, dict):
            row["mapping_by_site"] = {
                "restore": dict(legacy),
                "store77": dict(legacy),
            }
        else:
            row["mapping_by_site"] = {"restore": {}, "store77": {}}
    # migrate: mapping -> mapping_by_site
    for tid, row in (db.get("templates") or {}).items():
        if not isinstance(row, dict):
            continue
        if "mapping_by_site" in row and isinstance(row.get("mapping_by_site"), dict):
            continue
        legacy = row.get("mapping")
        if isinstance(legacy, dict):
            row["mapping_by_site"] = {
                "restore": dict(legacy),
                "store77": dict(legacy),
            }
        else:
            row["mapping_by_site"] = {"restore": {}, "store77": {}}
    if not isinstance(db.get("version"), int):
        db["version"] = 2
    if db["version"] < 2:
        db["version"] = 2

    return db


def save_competitor_mapping_db(db: Dict[str, Any]) -> None:
    if not isinstance(db, dict):
        db = _clone_default(DEFAULT_COMPETITOR_MAPPING)
    if "version" not in db:
        db["version"] = 2
    if "categories" not in db or not isinstance(db.get("categories"), dict):
        db["categories"] = {}
    if "templates" not in db or not isinstance(db.get("templates"), dict):
        db["templates"] = {}
    _write_json_atomic(COMPETITOR_MAPPING_FILE, db)


# =========================
# Dictionaries store (SOURCE OF TRUTH)
# =========================

DICTIONARIES_FILE = DATA_DIR / "dictionaries.json"
DICTS_DIR = DATA_DIR / "dicts"

# scope:
# - feature: характеристика
# - variant: параметр для вариантов
# - both: и то, и другое (по умолчанию для legacy)
ALLOWED_ATTR_TYPES = ("text", "number", "select", "bool", "date", "json")
ALLOWED_SCOPES = ("feature", "variant", "both")

DEFAULT_DICTIONARIES: Dict[str, Any] = {
    "version": 2,
    "items": [
        # {
        #   "id": "dict_storage",
        #   "title": "Встроенная память",
        #   "code": "storage",
        #   "attr_id": "attr_storage_xxxxxx",
        #   "type": "select"|"text"|"number"|"bool"|"date"|"json",
        #   "scope": "feature"|"variant"|"both",
        #   "items": [{"value": "128 ГБ", "count": 1, "last_seen": "", "sources": {}}],
        #   "aliases": {},
        #   "meta": {},
        #   "created_at": "",
        #   "updated_at": "",
        # }
    ],
}


def _migrate_dict_items(items: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not items:
        return out
    if isinstance(items, list):
        for it in items:
            if isinstance(it, str):
                v = it.strip()
                if v:
                    out.append({"value": v, "count": 0, "last_seen": None, "sources": {}})
            elif isinstance(it, dict):
                v = str(it.get("value") or "").strip()
                if not v:
                    continue
                out.append(
                    {
                        "value": v,
                        "count": int(it.get("count") or 0),
                        "last_seen": it.get("last_seen"),
                        "sources": it.get("sources") if isinstance(it.get("sources"), dict) else {},
                    }
                )
    return out


def _merge_dict_items(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for it in existing:
        v = str(it.get("value") or "").strip()
        if not v:
            continue
        by_key[v.lower()] = it
    for it in incoming:
        v = str(it.get("value") or "").strip()
        if not v:
            continue
        key = v.lower()
        if key not in by_key:
            by_key[key] = it
    return list(by_key.values())


def _migrate_dictionaries_db(db: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(db, dict):
        db = _clone_default(DEFAULT_DICTIONARIES)
    if "version" not in db or not isinstance(db.get("version"), int):
        db["version"] = 1
    if "items" not in db or not isinstance(db.get("items"), list):
        db["items"] = []

    for it in db.get("items", []):
        if not isinstance(it, dict):
            continue
        did = str(it.get("id") or "").strip()
        if not did:
            continue
        title = str(it.get("title") or did).strip()
        it["id"] = did
        it["title"] = title
        code = (it.get("code") or "").strip()
        if not code:
            if did.startswith("dict_"):
                code = did[len("dict_"):]
            else:
                code = slugify_code(title)
        it["code"] = code
        if not str(it.get("attr_id") or "").strip():
            it["attr_id"] = f"attr_{code}_{new_id()[:6]}"
        t = (it.get("type") or "select").strip()
        if t not in ALLOWED_ATTR_TYPES:
            t = "select"
        it["type"] = t
        scope = (it.get("scope") or "").strip()
        if scope not in ALLOWED_SCOPES:
            scope = "both"
        it["scope"] = scope
        it["dict_id"] = did
        if "items" in it and isinstance(it.get("items"), list):
            it["items"] = _migrate_dict_items(it.get("items"))
        elif isinstance(it.get("values"), list):
            it["items"] = _migrate_dict_items(it.get("values"))
        else:
            it["items"] = []
        if not isinstance(it.get("aliases"), dict):
            it["aliases"] = {}
        if not isinstance(it.get("meta"), dict):
            it["meta"] = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        if "created_at" not in it:
            it["created_at"] = ""
        if "updated_at" not in it:
            it["updated_at"] = ""

    if db["version"] < 2:
        db["version"] = 2
    return db


def load_dictionaries_db() -> Dict[str, Any]:
    db = _read_json(DICTIONARIES_FILE, DEFAULT_DICTIONARIES)
    db = _migrate_dictionaries_db(db)

    changed = False
    # one-time merge from legacy dict files
    try:
        for path in DICTS_DIR.glob("*.json"):
            raw = _read_json(path, {})
            if not isinstance(raw, dict):
                continue
            did = str(raw.get("id") or path.stem).strip()
            if not did:
                continue
            title = str(raw.get("title") or did).strip()
            items = _migrate_dict_items(raw.get("items"))
            aliases = raw.get("aliases") if isinstance(raw.get("aliases"), dict) else {}
            existing = next((x for x in db.get("items", []) if isinstance(x, dict) and x.get("id") == did), None)
            if existing is None:
                db["items"].append(
                    {
                        "id": did,
                        "title": title,
                        "items": items,
                        "aliases": aliases,
                        "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
                        "created_at": raw.get("created_at") or "",
                        "updated_at": raw.get("updated_at") or "",
                    }
                )
                changed = True
            else:
                merged = _merge_dict_items(existing.get("items", []), items)
                if len(merged) != len(existing.get("items", [])):
                    existing["items"] = merged
                    changed = True
    except Exception:
        pass

    if changed:
        save_dictionaries_db(db)

    return db


def save_dictionaries_db(db: Dict[str, Any]) -> None:
    db = _migrate_dictionaries_db(db)
    _write_json_atomic(DICTIONARIES_FILE, db)


def _norm_title(s: str) -> str:
    s = (s or "").strip().lower()
    s = " ".join(s.split())
    return s


def suggest_attributes(q: str, limit: int = 8) -> list[dict]:
    qn = _norm_title(q)
    if not qn:
        return []

    db = load_dictionaries_db()
    items = db.get("items", []) or []

    def score(it: dict) -> tuple[int, int]:
        t = _norm_title(it.get("title") or "")
        c = (it.get("code") or "").lower()
        s = 0
        if t.startswith(qn) or c.startswith(qn):
            s += 100
        if qn in t or qn in c:
            s += 50
        return (-s, len(t))

    filtered = []
    for it in items:
        if not isinstance(it, dict):
            continue
        t = _norm_title(it.get("title") or "")
        c = (it.get("code") or "").lower()
        if qn in t or qn in c:
            filtered.append(
                {
                    "id": it.get("attr_id") or it.get("id"),
                    "title": it.get("title") or "",
                    "code": it.get("code") or "",
                    "type": it.get("type"),
                    "scope": it.get("scope"),
                    "dict_id": it.get("id"),
                }
            )

    filtered.sort(key=score)
    return filtered[: max(1, min(50, int(limit or 8)))]


def _ensure_dict_file(dict_id: str, title: str, type_: Optional[str] = None, scope: Optional[str] = None) -> None:
    db = load_dictionaries_db()
    for it in db.get("items", []):
        if isinstance(it, dict) and str(it.get("id") or "").strip() == dict_id:
            return
    code = dict_id[len("dict_"):] if dict_id.startswith("dict_") else slugify_code(title)
    db["items"].append(
        {
            "id": dict_id,
            "title": title,
            "code": code,
            "attr_id": f"attr_{code}_{new_id()[:6]}",
            "type": type_ or "select",
            "scope": scope or "both",
            "items": [],
            "aliases": {},
            "meta": {},
            "created_at": "",
            "updated_at": "",
        }
    )
    save_dictionaries_db(db)


def ensure_global_attribute(
    title: str,
    type_: str,
    code: Optional[str] = None,
    scope: str = "both",
) -> dict:
    """
    Создаёт параметр в dictionaries.json при отсутствии.
    """
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")

    type_ = (type_ or "text").strip()
    if type_ not in ALLOWED_ATTR_TYPES:
        type_ = "text"

    scope = (scope or "both").strip()
    if scope not in ALLOWED_SCOPES:
        scope = "both"

    db = load_dictionaries_db()
    items = db.get("items", []) or []

    final_code = (code or "").strip() or slugify_code(title)
    canonical_dict_id = f"dict_{final_code}"
    tn = _norm_title(title)
    service_codes = {"sku_pim", "sku_gt", "barcode"}

    for it in items:
        if not isinstance(it, dict):
            continue
        item_id = str(it.get("id") or "").strip()
        item_code = str(it.get("code") or "").strip().lower()
        if item_id != canonical_dict_id and item_code != final_code.lower():
            continue
        meta = it.get("meta")
        if final_code.lower() in service_codes and (not isinstance(meta, dict) or not meta.get("service")):
            it["meta"] = {**(meta or {}), "service": True}
        cur_scope = (it.get("scope") or "both").strip()
        if cur_scope not in ALLOWED_SCOPES:
            cur_scope = "both"
        if cur_scope != "both" and scope == "both":
            it["scope"] = "both"
        if (it.get("type") or "") not in ALLOWED_ATTR_TYPES:
            it["type"] = type_
        it["title"] = title
        it["code"] = final_code
        it["dict_id"] = canonical_dict_id
        it["attr_id"] = it.get("attr_id") or f"attr_{final_code}_{new_id()[:6]}"
        it["updated_at"] = ""
        save_dictionaries_db(db)
        return {
            "id": it.get("attr_id") or it.get("id"),
            "title": it.get("title"),
            "code": it.get("code"),
            "type": it.get("type"),
            "scope": it.get("scope"),
            "dict_id": it.get("id"),
        }

    for it in items:
        if _norm_title(it.get("title") or "") == tn:
            code = (it.get("code") or "").strip().lower()
            if code in service_codes:
                meta = it.get("meta")
                if not isinstance(meta, dict) or not meta.get("service"):
                    it["meta"] = {**(meta or {}), "service": True}
                    save_dictionaries_db(db)
            cur_scope = (it.get("scope") or "both").strip()
            if cur_scope not in ALLOWED_SCOPES:
                cur_scope = "both"
            if cur_scope != "both" and scope == "both":
                it["scope"] = "both"
            if (it.get("type") or "") not in ALLOWED_ATTR_TYPES:
                it["type"] = "select"
            if not it.get("dict_id"):
                it["dict_id"] = it.get("id")
            it["updated_at"] = ""
            save_dictionaries_db(db)
            return {
                "id": it.get("attr_id") or it.get("id"),
                "title": it.get("title"),
                "code": it.get("code"),
                "type": it.get("type"),
                "scope": it.get("scope"),
                "dict_id": it.get("id"),
            }

    attr_id = f"attr_{final_code}_{new_id()[:6]}"

    dict_id = None
    if type_ == "select":
        dict_id = f"dict_{final_code}"
        _ensure_dict_file(dict_id, title, type_=type_, scope=scope)
    else:
        dict_id = f"dict_{final_code}"
        _ensure_dict_file(dict_id, title, type_=type_, scope=scope)

    it = next((x for x in items if isinstance(x, dict) and x.get("id") == dict_id), None)
    if not it:
        it = {
            "id": dict_id,
            "title": title,
            "code": final_code,
            "attr_id": attr_id,
            "type": type_,
            "scope": scope,
            "dict_id": dict_id,
            "items": [],
            "aliases": {},
            "meta": {},
            "created_at": "",
            "updated_at": "",
        }
        items.append(it)
    it["attr_id"] = it.get("attr_id") or attr_id
    it["type"] = type_
    it["scope"] = scope
    it["dict_id"] = dict_id
    if final_code.lower() in service_codes:
        it["meta"] = {**(it.get("meta") or {}), "service": True}

    db["items"] = items
    save_dictionaries_db(db)
    return {
        "id": it.get("attr_id") or it.get("id"),
        "title": it.get("title"),
        "code": it.get("code"),
        "type": it.get("type"),
        "scope": it.get("scope"),
        "dict_id": it.get("id"),
    }


# =========================
# Dictionaries helpers
# =========================

def dict_path(dict_id: str) -> Path:
    dict_id = (dict_id or "").strip()
    return DICTS_DIR / f"{dict_id}.json"


def dict_exists(dict_id: str) -> bool:
    did = (dict_id or "").strip()
    if not did:
        return False
    db = load_dictionaries_db()
    return any(isinstance(it, dict) and str(it.get("id") or "").strip() == did for it in db.get("items", []))


def load_dict(dict_id: str) -> Dict[str, Any]:
    did = (dict_id or "").strip()
    db = load_dictionaries_db()
    for it in db.get("items", []):
        if isinstance(it, dict) and str(it.get("id") or "").strip() == did:
            return it
    doc = {"id": did, "title": did, "items": [], "aliases": {}, "meta": {}, "created_at": "", "updated_at": ""}
    db.get("items", []).append(doc)
    save_dictionaries_db(db)
    return doc


def save_dict(doc: Dict[str, Any]) -> None:
    did = str(doc.get("id") or "").strip()
    if not did:
        return
    db = load_dictionaries_db()
    items = db.get("items", [])
    replaced = False
    for i, it in enumerate(items):
        if isinstance(it, dict) and str(it.get("id") or "").strip() == did:
            items[i] = doc
            replaced = True
            break
    if not replaced:
        items.append(doc)
    db["items"] = items
    save_dictionaries_db(db)


def ensure_dict_value(dict_id: str, value: str) -> Dict[str, Any]:
    """
    Добавляет значение в dict.items, если его ещё нет (по точному совпадению).
    Возвращает обновлённый dict.
    """
    value = (value or "").strip()
    if not value:
        return load_dict(dict_id)

    doc = load_dict(dict_id)
    items = doc.get("items", []) or []
    if not isinstance(items, list):
        items = []

    def _item_value(x: Any) -> str:
        if isinstance(x, dict):
            return str(x.get("value") or "").strip()
        return str(x or "").strip()

    exists = any(_item_value(x) == value for x in items)
    if not exists:
        items.append({"value": value, "count": 0, "last_seen": None, "sources": {}})
        doc["items"] = items
        save_dict(doc)

    return doc
