# backend/app/api/routes/attributes.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query, HTTPException
from pydantic import BaseModel, Field

from app.storage.json_store import (
    suggest_attributes,
    ensure_global_attribute,
    load_dictionaries_db,
    save_dictionaries_db,
)

router = APIRouter(tags=["attributes"])


# =========================
# Models
# =========================

class AttributePatchReq(BaseModel):
    title: Optional[str] = None
    code: Optional[str] = None
    type: Optional[str] = None       # text|number|select|bool|date|json
    scope: Optional[str] = None      # feature|variant|both
    dict_id: Optional[str] = None    # only for select


class AttributeEnsureReq(BaseModel):
    title: str = Field(min_length=1)
    type: str = Field(default="text")
    code: Optional[str] = None
    scope: str = Field(default="both")  # feature|variant|both


# =========================
# Helpers
# =========================

_ALLOWED_TYPES = {"text", "number", "select", "bool", "date", "json"}
_ALLOWED_SCOPES = {"feature", "variant", "both"}


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _find_attr(db: Dict[str, Any], attr_id: str) -> Optional[Dict[str, Any]]:
    for it in (db.get("items") or []):
        if not isinstance(it, dict):
            continue
        if str(it.get("attr_id") or "") == str(attr_id):
            return it
    return None


# =========================
# Existing endpoints
# =========================

@router.get("/attributes/suggest")
def attributes_suggest(
    q: str = Query("", min_length=0),
    limit: int = Query(8, ge=1, le=50),
):
    items = suggest_attributes(q, limit=limit)
    return {"items": items}


@router.post("/attributes/ensure")
def attributes_ensure(payload: AttributeEnsureReq = Body(...)):
    title = _norm(payload.title)
    type_ = _norm(payload.type) or "text"
    code = _norm(payload.code) or None
    scope = _norm(payload.scope) or "both"

    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if type_ not in _ALLOWED_TYPES:
        type_ = "text"
    if scope not in _ALLOWED_SCOPES:
        scope = "both"

    try:
        it = ensure_global_attribute(title=title, type_=type_, code=code, scope=scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"attribute": it}


# =========================
# New endpoints (master list)
# =========================

@router.get("/attributes")
def attributes_list(
    q: str = Query("", min_length=0),
    scope: Optional[str] = Query(None),   # feature|variant|both
    type: Optional[str] = Query(None),    # text|number|select|bool|date|json
    limit: int = Query(200, ge=1, le=10000),
):
    db = load_dictionaries_db()
    items = [x for x in (db.get("items") or []) if isinstance(x, dict)]

    qn = _norm(q).lower()
    if qn:
        items = [
            it for it in items
            if qn in str(it.get("title") or "").lower()
            or qn in str(it.get("code") or "").lower()
        ]

    if scope:
        sc = _norm(scope)
        if sc not in _ALLOWED_SCOPES:
            raise HTTPException(status_code=400, detail="BAD_SCOPE")
        if sc == "both":
            # both = всё
            pass
        else:
            # показываем scope=both + scope=sc
            items = [it for it in items if (it.get("scope") in (sc, "both"))]

    if type:
        tp = _norm(type)
        if tp not in _ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="BAD_TYPE")
        items = [it for it in items if str(it.get("type") or "") == tp]

    # лёгкая сортировка: title asc
    items.sort(key=lambda x: str(x.get("title") or "").lower())

    out = [
        {
            "id": it.get("attr_id") or it.get("id"),
            "title": it.get("title"),
            "code": it.get("code"),
            "type": it.get("type"),
            "scope": it.get("scope"),
            "dict_id": it.get("id"),
            "param_group": ((it.get("meta") or {}).get("param_group") if isinstance(it.get("meta"), dict) else None),
        }
        for it in items[:limit]
    ]

    return {"items": out, "total": len(items)}


@router.get("/attributes/{attr_id}")
def attributes_get(attr_id: str):
    db = load_dictionaries_db()
    it = _find_attr(db, attr_id)
    if not it:
        raise HTTPException(status_code=404, detail="ATTRIBUTE_NOT_FOUND")
    return {
        "attribute": {
            "id": it.get("attr_id") or it.get("id"),
            "title": it.get("title"),
            "code": it.get("code"),
            "type": it.get("type"),
            "scope": it.get("scope"),
            "dict_id": it.get("id"),
        }
    }


@router.patch("/attributes/{attr_id}")
def attributes_patch(attr_id: str, payload: AttributePatchReq):
    db = load_dictionaries_db()
    it = _find_attr(db, attr_id)
    if not it:
        raise HTTPException(status_code=404, detail="ATTRIBUTE_NOT_FOUND")

    # применяем патч
    if payload.title is not None:
        t = _norm(payload.title)
        if not t:
            raise HTTPException(status_code=400, detail="TITLE_REQUIRED")
        it["title"] = t

    if payload.code is not None:
        c = _norm(payload.code)
        if not c:
            raise HTTPException(status_code=400, detail="CODE_REQUIRED")
        it["code"] = c

    if payload.type is not None:
        tp = _norm(payload.type)
        if tp not in _ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="BAD_TYPE")
        it["type"] = tp

    if payload.scope is not None:
        sc = _norm(payload.scope)
        if sc not in _ALLOWED_SCOPES:
            raise HTTPException(status_code=400, detail="BAD_SCOPE")
        it["scope"] = sc

    if payload.dict_id is not None:
        did = _norm(payload.dict_id)
        it["dict_id"] = did or it.get("id")

    save_dictionaries_db(db)
    return {
        "attribute": {
            "id": it.get("attr_id") or it.get("id"),
            "title": it.get("title"),
            "code": it.get("code"),
            "type": it.get("type"),
            "scope": it.get("scope"),
            "dict_id": it.get("id"),
        }
    }
