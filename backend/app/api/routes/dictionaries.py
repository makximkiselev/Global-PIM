# backend/app/api/routes/dictionaries.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from app.storage.json_store import (
    load_templates_db,
    save_templates_db,
    load_dictionaries_db,
    save_dictionaries_db,
    new_id,
    slugify_code,
)
from app.core.json_store import DATA_DIR, read_doc
from app.storage.relational_pim_store import load_catalog_nodes

router = APIRouter(tags=["dictionaries"])
CATALOG_NODES_PATH = DATA_DIR / "catalog_nodes.json"


# =========================
# IO
# =========================

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _default_dict(dict_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    now = _utc_now_iso()
    code = dict_id[len("dict_"):] if dict_id.startswith("dict_") else slugify_code(title or dict_id)
    return {
        "id": dict_id,
        "title": (title or dict_id).strip(),
        "code": code,
        "attr_id": f"attr_{code}_{new_id()[:6]}",
        "type": "select",
        "scope": "both",
        "dict_id": dict_id,
        "items": [],          # list[{"value": str, "count": int, "last_seen": str|None, "sources": {..}}]
        "aliases": {},        # { "alias": "canonical" }
        "meta": {},
        "created_at": now,
        "updated_at": now,
    }


def _load_dict(dict_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    did = (dict_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="dict_id is required")
    db = load_dictionaries_db()
    for it in db.get("items", []):
        if isinstance(it, dict) and str(it.get("id") or "").strip() == did:
            return it
    d = _default_dict(did, title=title)
    db.setdefault("items", []).append(d)
    save_dictionaries_db(db)
    return d


def _save_dict(d: Dict[str, Any]) -> None:
    did = str(d.get("id") or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="BAD_DICT_ID")
    db = load_dictionaries_db()
    items = db.get("items", [])
    replaced = False
    for i, it in enumerate(items):
        if isinstance(it, dict) and str(it.get("id") or "").strip() == did:
            items[i] = d
            replaced = True
            break
    if not replaced:
        items.append(d)
    db["items"] = items
    save_dictionaries_db(db)


# =========================
# Normalize / helpers
# =========================

def _norm_value_key(value: str) -> str:
    v = (value or "").strip().lower()
    v = " ".join(v.split())
    return v


def _coerce_items(items: Any) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Канон:
      list[{"value": str, "count": int, "last_seen": str|None, "sources": dict}]
    Поддержка legacy list[str]
    """
    out: List[Dict[str, Any]] = []
    changed = False

    if not items:
        return [], False

    if isinstance(items, list):
        for it in items:
            if isinstance(it, str):
                s = it.strip()
                if not s:
                    changed = True
                    continue
                out.append({"value": s, "count": 1, "last_seen": None, "sources": {}})
                changed = True
            elif isinstance(it, dict):
                s = str(it.get("value") or "").strip()
                if not s:
                    changed = True
                    continue
                out.append(
                    {
                        "value": s,
                        "count": int(it.get("count") or 1),
                        "last_seen": (it.get("last_seen") or None),
                        "sources": it.get("sources") if isinstance(it.get("sources"), dict) else {},
                    }
                )
            else:
                changed = True
        return out, changed

    return [], True


def _items_to_public(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        items,
        key=lambda x: (-int(x.get("count") or 0), (x.get("value") or "").lower()),
    )


def _iso_max(a: Optional[str], b: Optional[str]) -> Optional[str]:
    sa = str(a or "").strip()
    sb = str(b or "").strip()
    if not sa and not sb:
        return None
    if not sa:
        return sb
    if not sb:
        return sa
    return sa if sa >= sb else sb


def _existing_category_ids() -> set[str]:
    nodes = load_catalog_nodes()
    out: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict):
            continue
        cid = str(n.get("id") or "").strip()
        if cid:
            out.add(cid)
    return out


def _cleanup_orphan_templates(existing_category_ids: set[str]) -> Dict[str, Any]:
    """
    Чистит templates.json от шаблонов/маппингов, где category_id уже не существует.
    Возвращает уже очищенный db.
    """
    db = load_templates_db()
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    attrs = db.get("attributes") if isinstance(db.get("attributes"), dict) else {}
    cat_to_tpl = db.get("category_to_template") if isinstance(db.get("category_to_template"), dict) else {}
    cat_to_tpls = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}

    removed_tids: set[str] = set()
    changed = False

    for tid, t in list(templates.items()):
        if not isinstance(t, dict):
            templates.pop(tid, None)
            removed_tids.add(str(tid))
            changed = True
            continue
        cid = str(t.get("category_id") or "").strip()
        if not cid or cid not in existing_category_ids:
            templates.pop(tid, None)
            removed_tids.add(str(tid))
            changed = True

    for tid in removed_tids:
        if tid in attrs:
            attrs.pop(tid, None)
            changed = True

    for cid in list(cat_to_tpl.keys()):
        tid = str(cat_to_tpl.get(cid) or "").strip()
        if cid not in existing_category_ids or (tid and tid in removed_tids):
            cat_to_tpl.pop(cid, None)
            changed = True

    for cid in list(cat_to_tpls.keys()):
        if cid not in existing_category_ids:
            cat_to_tpls.pop(cid, None)
            changed = True
            continue
        arr = cat_to_tpls.get(cid)
        if not isinstance(arr, list):
            cat_to_tpls.pop(cid, None)
            changed = True
            continue
        next_arr = [str(x) for x in arr if str(x) and str(x) not in removed_tids and str(x) in templates]
        if next_arr != arr:
            if next_arr:
                cat_to_tpls[cid] = next_arr
            else:
                cat_to_tpls.pop(cid, None)
            changed = True

    if changed:
        db["templates"] = templates
        db["attributes"] = attrs
        db["category_to_template"] = cat_to_tpl
        db["category_to_templates"] = cat_to_tpls
        save_templates_db(db)

    return db


# =========================
# DTOs
# =========================

class EnsureDictReq(BaseModel):
    title: Optional[str] = None


class BulkCreateReq(BaseModel):
    titles: List[str] = Field(default_factory=list)
    type: Optional[str] = Field(default="select")
    meta: Optional[Dict[str, Any]] = None  # пока храним только если надо (можно не использовать)


class EnsureValueReq(BaseModel):
    value: str = Field(min_length=1)
    source: Optional[str] = None


class RenameValueReq(BaseModel):
    from_value: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)


class DeleteValueReq(BaseModel):
    value: str = Field(min_length=1)


class DedupeReq(BaseModel):
    apply: bool = False


class ImportValuesReq(BaseModel):
    values: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    replace: bool = False


# =========================
# Public API
# =========================

@router.get("/dictionaries")
def list_dictionaries(include_service: bool = Query(False)):
    """
    Список словарей (без items).
    """
    out: List[Dict[str, Any]] = []
    existing_categories = _existing_category_ids()
    tpl_db = _cleanup_orphan_templates(existing_categories)
    tpl_items = tpl_db.get("templates") or {}
    tpl_attrs = tpl_db.get("attributes") or {}
    dict_to_templates: Dict[str, List[str]] = {}
    dict_to_categories: Dict[str, set] = {}
    dict_title_hints: Dict[str, str] = {}

    service_codes = {"sku_gt", "barcode"}

    if isinstance(tpl_attrs, dict):
        for tid, attrs in tpl_attrs.items():
            if not isinstance(attrs, list):
                continue
            t = tpl_items.get(tid) if isinstance(tpl_items, dict) else {}
            tname = str((t or {}).get("name") or tid)
            tcat = str((t or {}).get("category_id") or "")
            if not tcat or tcat not in existing_categories:
                continue
            for a in attrs:
                if not isinstance(a, dict):
                    continue
                code = (a.get("code") or "").strip()
                opts = a.get("options") if isinstance(a.get("options"), dict) else {}
                did = (opts.get("dict_id") or a.get("dict_id") or "").strip()
                candidates = set()
                if did:
                    candidates.add(did)
                if code:
                    candidates.add(f"dict_{code}")
                for cand in candidates:
                    if not cand:
                        continue
                    if str(a.get("name") or "").strip() and cand not in dict_title_hints:
                        dict_title_hints[cand] = str(a.get("name") or "").strip()
                    dict_to_templates.setdefault(cand, [])
                    if tname not in dict_to_templates[cand]:
                        dict_to_templates[cand].append(tname)
                    if tcat:
                        dict_to_categories.setdefault(cand, set()).add(tcat)

    # ensure dicts exist for all mapped attributes
    for did in dict_to_templates.keys():
        _load_dict(did, title=dict_title_hints.get(did))

    db = load_dictionaries_db()
    seen_title_keys: set[str] = set()
    for d in db.get("items", []):
        if not isinstance(d, dict):
            continue
        did = str(d.get("id") or "").strip()
        if not did:
            continue
        title = str(d.get("title") or did).strip()
        code = str(d.get("code") or "").strip()
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        title_hint = dict_title_hints.get(did) or ""
        # Repair old technical titles on the fly once.
        if title.startswith("dict_") and title_hint:
            d["title"] = title_hint
            d["updated_at"] = _utc_now_iso()
            _save_dict(d)
            title = title_hint
        if not code and did.startswith("dict_"):
            code = did[len("dict_"):]
        if code in service_codes and not meta.get("service"):
            meta["service"] = True
            meta["required"] = True
            d["meta"] = meta
            d["updated_at"] = _utc_now_iso()
            _save_dict(d)
        title_key = " ".join(str(title or "").strip().lower().split())
        if bool(meta.get("service")) and not include_service:
            continue
        if code == "sku_pim" or title_key == "sku pim":
            continue
        if title_key and title_key in seen_title_keys:
            continue
        if title_key:
            seen_title_keys.add(title_key)
        items, changed = _coerce_items(d.get("items"))
        if changed:
            d["items"] = items
            d["updated_at"] = _utc_now_iso()
            _save_dict(d)
        out.append(
            {
                "id": did,
                "title": title,
                "code": code,
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
                "size": len(items),
                "templates": sorted(dict_to_templates.get(did, []), key=lambda x: x.lower()),
                "category_count": len(dict_to_categories.get(did, set())),
                "type": d.get("type"),
                "scope": d.get("scope"),
                "meta": {
                    "service": bool(meta.get("service")),
                    "required": bool(meta.get("required") or meta.get("service")),
                    "param_group": str(meta.get("param_group") or "").strip(),
                },
            }
        )

    out.sort(key=lambda x: (x.get("title") or x.get("id") or "").lower())
    return {"items": out}


@router.get("/dictionaries/{dict_id}")
def get_dictionary(dict_id: str):
    d = _load_dict(dict_id)
    items, changed = _coerce_items(d.get("items"))
    d["items"] = _items_to_public(items)

    if changed:
        d["updated_at"] = _utc_now_iso()
        _save_dict(d)

    return {"item": d}


class DictMetaPatchReq(BaseModel):
    title: Optional[str] = None
    service: Optional[bool] = None
    required: Optional[bool] = None
    param_group: Optional[str] = None
    export_map: Optional[Dict[str, Dict[str, Optional[str]]]] = None


@router.patch("/dictionaries/{dict_id}")
def patch_dictionary(dict_id: str, payload: DictMetaPatchReq = Body(default=DictMetaPatchReq())):
    d = _load_dict(dict_id)
    meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
    changed = False
    if payload.title is not None:
        title = str(payload.title or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="TITLE_REQUIRED")
        d["title"] = title
        changed = True
    if payload.service is not None:
        meta["service"] = bool(payload.service)
        meta["required"] = bool(payload.service)
        changed = True
    if payload.required is not None:
        meta["required"] = bool(payload.required)
        meta["service"] = bool(payload.required)  # backward compatibility
        changed = True
    if payload.param_group is not None:
        pg = str(payload.param_group or "").strip()
        if pg:
            meta["param_group"] = pg
        else:
            meta.pop("param_group", None)
        changed = True
    if payload.export_map is not None:
        raw_export = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
        next_export: Dict[str, Dict[str, str]] = {}
        for provider, cur in raw_export.items():
            if not isinstance(cur, dict):
                continue
            provider_map: Dict[str, str] = {}
            for key, value in cur.items():
                nk = _norm_value_key(str(key or ""))
                vv = str(value or "").strip()
                if nk and vv:
                    provider_map[nk] = vv
            if provider_map:
                next_export[str(provider)] = provider_map

        for provider, patch_map in payload.export_map.items():
            pcode = str(provider or "").strip()
            if not pcode:
                continue
            current = dict(next_export.get(pcode) or {})
            if not isinstance(patch_map, dict):
                continue
            for canonical_value, provider_value in patch_map.items():
                ckey = _norm_value_key(str(canonical_value or ""))
                if not ckey:
                    continue
                mapped = str(provider_value or "").strip() if provider_value is not None else ""
                if mapped:
                    current[ckey] = mapped
                else:
                    current.pop(ckey, None)
            if current:
                next_export[pcode] = current
            else:
                next_export.pop(pcode, None)
        meta["export_map"] = next_export
        changed = True
    if changed:
        d["meta"] = meta
        d["updated_at"] = _utc_now_iso()
        _save_dict(d)
    return {"item": d}


@router.post("/dictionaries/{dict_id}/ensure")
def ensure_dictionary(dict_id: str, payload: EnsureDictReq = Body(default=EnsureDictReq())):
    """
    Создаёт dict-файл если нет. Не затирает items/aliases.
    """
    dict_id = (dict_id or "").strip()
    if not dict_id:
        raise HTTPException(status_code=400, detail="dict_id is required")
    d = _load_dict(dict_id)
    if payload.title and not str(d.get("title") or "").strip():
        d["title"] = payload.title.strip()
        d["updated_at"] = _utc_now_iso()
        _save_dict(d)
    return {"item": d}


@router.post("/dictionaries/bulk")
def bulk_create_dictionaries(payload: BulkCreateReq = Body(...)):
    titles = [str(x or "").strip() for x in (payload.titles or [])]
    titles = [t for t in titles if t]
    if not titles:
        raise HTTPException(status_code=400, detail="EMPTY_TITLES")

    req_type = (payload.type or "select").strip()
    if req_type not in {"text", "number", "select", "bool", "date", "json"}:
        raise HTTPException(status_code=400, detail="BAD_TYPE")

    db = load_dictionaries_db()
    items = db.get("items", []) or []
    now = _utc_now_iso()

    created = 0
    updated = 0
    affected: List[Dict[str, Any]] = []

    for title in titles:
        code = slugify_code(title)
        dict_id = f"dict_{code}"

        # ensure dict entry exists (do not overwrite items)
        d = _load_dict(dict_id)
        if not str(d.get("title") or "").strip():
            d["title"] = title
        d["updated_at"] = now
        _save_dict(d)

        entry = None
        for it in items:
            if not isinstance(it, dict):
                continue
            if (it.get("id") or "") == dict_id or (it.get("code") or "") == code:
                entry = it
                break

        if not entry:
            entry = {
                "id": dict_id,
                "title": title,
                "code": code,
                "attr_id": f"attr_{code}_{new_id()[:6]}",
                "type": req_type,
                "scope": "both",
                "dict_id": dict_id,
                "items": [],
                "aliases": {},
                "meta": payload.meta or {},
                "created_at": now,
                "updated_at": now,
            }
            items.append(entry)
            created += 1
        else:
            if not str(entry.get("title") or "").strip():
                entry["title"] = title
            if not entry.get("dict_id"):
                entry["dict_id"] = dict_id
            if entry.get("type") != req_type:
                entry["type"] = req_type
            entry["updated_at"] = now
            updated += 1

        affected.append({
            "id": str(entry.get("id") or dict_id),
            "title": str(entry.get("title") or title),
            "code": str(entry.get("code") or code),
            "created_at": entry.get("created_at"),
            "updated_at": entry.get("updated_at"),
            "size": len(entry.get("items") or []),
            "templates": [],
            "category_count": 0,
            "type": entry.get("type"),
            "scope": entry.get("scope"),
            "meta": entry.get("meta") if isinstance(entry.get("meta"), dict) else {},
        })

    db["items"] = items
    save_dictionaries_db(db)
    return {"ok": True, "created": created, "updated": updated, "items": affected}


@router.delete("/dictionaries/{dict_id}")
def delete_dictionary(dict_id: str):
    db = load_dictionaries_db()
    items = [
        x
        for x in (db.get("items") or [])
        if not (isinstance(x, dict) and str(x.get("id") or "") == dict_id)
    ]
    db["items"] = items
    save_dictionaries_db(db)
    return {"ok": True}


# =========================
# Values editing
# =========================

@router.post("/dictionaries/{dict_id}/values/ensure")
def ensure_dictionary_value(dict_id: str, payload: EnsureValueReq):
    """
    Добавляет значение или инкрементит count по exact normalize.
    """
    d = _load_dict(dict_id)
    items, _ = _coerce_items(d.get("items"))
    key = _norm_value_key(payload.value)

    if not key:
        raise HTTPException(status_code=400, detail="value is required")

    found = None
    for it in items:
        if _norm_value_key(it.get("value") or "") == key:
            found = it
            break

    now = _utc_now_iso()

    if not found:
        found = {"value": payload.value.strip(), "count": 1, "last_seen": now, "sources": {}}
        items.append(found)
    else:
        found["count"] = int(found.get("count") or 0) + 1
        found["last_seen"] = now
        # display: если пришло "красивее" — обновим
        cand = payload.value.strip()
        if len(cand) >= len(str(found.get("value") or "")):
            found["value"] = cand

    if payload.source:
        srcs = found.get("sources") if isinstance(found.get("sources"), dict) else {}
        srcs[payload.source] = int(srcs.get(payload.source, 0)) + 1
        found["sources"] = srcs

    d["items"] = items
    d["updated_at"] = now
    _save_dict(d)

    return {"ok": True}


@router.post("/dictionaries/{dict_id}/values")
def add_dictionary_value(dict_id: str, payload: EnsureValueReq):
    """
    Backward-compatible endpoint for UI:
    equivalent to POST /values/ensure.
    """
    return ensure_dictionary_value(dict_id, payload)


@router.post("/dictionaries/{dict_id}/values/import")
def import_dictionary_values(dict_id: str, payload: ImportValuesReq):
    """
    Импортирует список значений одним запросом.
    """
    values = payload.values or []
    if not isinstance(values, list):
        raise HTTPException(status_code=400, detail="values must be list")

    d = _load_dict(dict_id)
    items, _ = _coerce_items(d.get("items"))
    now = _utc_now_iso()

    seen_batch: Dict[str, str] = {}
    for raw in values:
        s = str(raw or "").strip()
        if not s:
            continue
        key = _norm_value_key(s)
        if not key:
            continue
        if key not in seen_batch:
            seen_batch[key] = s

    if not seen_batch:
        return {"ok": True, "added": 0, "updated": 0, "removed": 0}

    added = 0
    updated = 0
    removed = 0

    if payload.replace:
        new_items: List[Dict[str, Any]] = []
        for key, val in seen_batch.items():
            found = None
            for it in items:
                if _norm_value_key(it.get("value") or "") == key:
                    found = it
                    break
            if not found:
                found = {"value": val.strip(), "count": 1, "last_seen": now, "sources": {}}
                added += 1
            else:
                cand = val.strip()
                if len(cand) >= len(str(found.get("value") or "")):
                    found["value"] = cand
                found["last_seen"] = now
                updated += 1

            if payload.source:
                srcs = found.get("sources") if isinstance(found.get("sources"), dict) else {}
                srcs[payload.source] = int(srcs.get(payload.source, 0)) + 1
                found["sources"] = srcs
            new_items.append(found)

        removed = max(len(items) - len(new_items), 0)
        d["items"] = new_items
    else:
        for key, val in seen_batch.items():
            found = None
            for it in items:
                if _norm_value_key(it.get("value") or "") == key:
                    found = it
                    break

            if not found:
                found = {"value": val.strip(), "count": 1, "last_seen": now, "sources": {}}
                items.append(found)
                added += 1
            else:
                found["count"] = int(found.get("count") or 0) + 1
                found["last_seen"] = now
                cand = val.strip()
                if len(cand) >= len(str(found.get("value") or "")):
                    found["value"] = cand
                updated += 1

            if payload.source:
                srcs = found.get("sources") if isinstance(found.get("sources"), dict) else {}
                srcs[payload.source] = int(srcs.get(payload.source, 0)) + 1
                found["sources"] = srcs

        d["items"] = items
    d["updated_at"] = now
    _save_dict(d)

    return {"ok": True, "added": added, "updated": updated, "removed": removed}


@router.put("/dictionaries/{dict_id}/values/rename")
def rename_dictionary_value(dict_id: str, payload: RenameValueReq):
    """
    Переименовать значение. Если to уже существует — merge.
    """
    d = _load_dict(dict_id)
    items, _ = _coerce_items(d.get("items"))

    from_key = _norm_value_key(payload.from_value)
    to_key = _norm_value_key(payload.to)

    if not from_key or not to_key:
        raise HTTPException(status_code=400, detail="from and to are required")
    if from_key == to_key:
        return {"ok": True}

    src = None
    dst = None
    for it in items:
        k = _norm_value_key(it.get("value") or "")
        if k == from_key:
            src = it
        elif k == to_key:
            dst = it

    if not src:
        raise HTTPException(status_code=404, detail="VALUE_NOT_FOUND")

    now = _utc_now_iso()

    if not dst:
        src["value"] = payload.to.strip()
        src["last_seen"] = src.get("last_seen") or now
    else:
        dst["count"] = int(dst.get("count") or 0) + int(src.get("count") or 0)
        dst["last_seen"] = _iso_max(dst.get("last_seen"), src.get("last_seen")) or now

        s1 = dst.get("sources") if isinstance(dst.get("sources"), dict) else {}
        s2 = src.get("sources") if isinstance(src.get("sources"), dict) else {}
        for k, v in s2.items():
            s1[k] = int(s1.get(k, 0)) + int(v or 0)
        dst["sources"] = s1

        dst["value"] = payload.to.strip()

        # remove src
        items = [it for it in items if _norm_value_key(it.get("value") or "") != from_key]

    d["items"] = items
    d["updated_at"] = now
    _save_dict(d)

    return {"ok": True}


@router.delete("/dictionaries/{dict_id}/values")
def delete_dictionary_value(dict_id: str, payload: DeleteValueReq = Body(...)):
    """
    Удаляет значение по exact normalize.
    """
    d = _load_dict(dict_id)
    items, _ = _coerce_items(d.get("items"))

    key = _norm_value_key(payload.value)
    if not key:
        raise HTTPException(status_code=400, detail="value is required")

    new_items = [it for it in items if _norm_value_key(it.get("value") or "") != key]
    if len(new_items) == len(items):
        return {"ok": True}

    d["items"] = new_items
    d["updated_at"] = _utc_now_iso()
    _save_dict(d)

    return {"ok": True}


@router.post("/dictionaries/{dict_id}/dedupe")
def dedupe_dictionary_values(dict_id: str, payload: DedupeReq = Body(default=DedupeReq())):
    """
    Чистка дублей по exact normalize (preview/apply).
    """
    d = _load_dict(dict_id)
    items, _ = _coerce_items(d.get("items"))
    before_count = len(items)

    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for it in items:
        k = _norm_value_key(it.get("value") or "")
        if not k:
            continue
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(it)

    def _score(x: Dict[str, Any]) -> Tuple[int, int]:
        return (int(x.get("count") or 0), len(str(x.get("value") or "")))

    merges: List[Dict[str, Any]] = []
    new_items: List[Dict[str, Any]] = []

    for k in order:
        arr = groups.get(k) or []
        if not arr:
            continue

        keep = max(arr, key=_score)
        keep_out = dict(keep)
        keep_out["count"] = int(keep_out.get("count") or 0)
        keep_out["value"] = str(keep_out.get("value") or "").strip()
        keep_out["sources"] = keep_out.get("sources") if isinstance(keep_out.get("sources"), dict) else {}
        keep_out["last_seen"] = keep_out.get("last_seen") or None

        merged_names: List[str] = []
        merged_count = 0

        for it in arr:
            if it is keep:
                continue

            merged_names.append(str(it.get("value") or ""))

            c = int(it.get("count") or 0)
            if c:
                keep_out["count"] += c
                merged_count += c

            keep_out["last_seen"] = _iso_max(keep_out.get("last_seen"), it.get("last_seen"))

            s1 = keep_out.get("sources") if isinstance(keep_out.get("sources"), dict) else {}
            s2 = it.get("sources") if isinstance(it.get("sources"), dict) else {}
            for src, n in s2.items():
                s1[src] = int(s1.get(src, 0)) + int(n or 0)
            keep_out["sources"] = s1

            cand = str(it.get("value") or "").strip()
            if len(cand) > len(str(keep_out.get("value") or "")):
                keep_out["value"] = cand

        new_items.append(keep_out)

        if merged_names:
            merges.append(
                {
                    "keep": str(keep_out.get("value") or ""),
                    "merged": merged_names,
                    "merged_items": len(merged_names),
                    "merged_count": merged_count,
                    "last_seen": keep_out.get("last_seen"),
                }
            )

    new_items = _items_to_public(new_items)
    after_count = len(new_items)
    removed = max(0, before_count - after_count)

    if payload.apply:
        d["items"] = new_items
        d["updated_at"] = _utc_now_iso()
        _save_dict(d)

    return {
        "ok": True,
        "apply": payload.apply,
        "before_count": before_count,
        "after_count": after_count,
        "removed": removed,
        "merges": merges,
    }


# =========================
# Helpers for templates/parser (optional)
# =========================

def dict_id_for_attr(attr_code: str) -> str:
    c = (attr_code or "").strip()
    if not c:
        raise ValueError("attr_code is required")
    return f"dict_{c}"


def ensure_dictionaries_for_template_attrs(attributes: List[Dict[str, Any]]) -> int:
    """
    Для template attrs — гарантирует наличие dict_id и записи словаря.
    attributes: list[{code,type,title|name,options}]
    """
    if not attributes:
        return 0

    dict_db = load_dictionaries_db()
    dict_items = dict_db.get("items", []) if isinstance(dict_db, dict) else []
    attr_by_id = {}
    for it in dict_items or []:
        if not isinstance(it, dict):
            continue
        aid = (it.get("attr_id") or "").strip()
        if aid:
            attr_by_id[aid] = it

    n = 0
    for a in attributes:
        if not isinstance(a, dict):
            continue
        opts = a.get("options") if isinstance(a.get("options"), dict) else {}
        explicit_did = (opts.get("dict_id") or a.get("dict_id") or "").strip()
        if not explicit_did:
            aid = (opts.get("attribute_id") or a.get("attribute_id") or "").strip()
            if aid and aid in attr_by_id:
                explicit_did = (attr_by_id[aid].get("id") or "").strip()
        code = (a.get("code") or "").strip()
        if not code:
            continue

        title = (a.get("title") or a.get("name") or code).strip()
        did = explicit_did or dict_id_for_attr(code)

        # ensure dict entry
        d = _load_dict(did)
        cur_title = str(d.get("title") or "").strip()
        if title and (not cur_title or cur_title == did or cur_title.startswith("dict_")):
            d["title"] = title
        _save_dict(d)

        # write back dict_id to options
        opts.setdefault("dict_id", did)
        a["options"] = opts

        n += 1

    return n
