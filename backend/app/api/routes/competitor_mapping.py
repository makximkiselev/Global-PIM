# backend/app/api/routes/competitor_mapping.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from app.storage.json_store import (
    load_competitor_mapping_db,
    save_competitor_mapping_db,
    load_templates_db,
)
from app.core.value_mapping import canonicalize_dictionary_value

# ✅ Реальный извлекатель полей конкурента (Playwright + restore/store77 парсеры)
from app.core.competitors.extract_competitor_fields import (
    extract_competitor_fields,
    extract_competitor_content,
)

router = APIRouter(prefix="/competitor-mapping", tags=["competitor-mapping"])


# =========================
# helpers
# =========================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ALLOWED_SITES: Dict[str, set[str]] = {
    "restore": {"re-store.ru"},
    "store77": {"store77.net"},
}


def detect_site(url: str) -> Optional[str]:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]

    for site, domains in ALLOWED_SITES.items():
        if host in domains or any(host.endswith("." + d) for d in domains):
            return site
    return None


def _validate_links_keep_keys(links: Any) -> Dict[str, str]:
    """
    Возвращает нормализованные ссылки, проверяя домены.
    ✅ Ключи всегда присутствуют: restore/store77.
    ✅ Пустые значения допускаем и сохраняем как "".
    """
    out: Dict[str, str] = {k: "" for k in ALLOWED_SITES.keys()}
    links = links or {}

    if not isinstance(links, dict):
        raise HTTPException(status_code=400, detail="links must be an object")

    # запретим неизвестные ключи
    for k in links.keys():
        if k not in ALLOWED_SITES:
            raise HTTPException(status_code=400, detail=f"Unknown site key: {k}")

    for k in out.keys():
        v = links.get(k)
        url = (str(v).strip() if v is not None else "")
        if not url:
            out[k] = ""
            continue

        site = detect_site(url)
        if site != k:
            raise HTTPException(
                status_code=400,
                detail="Парсинг запрещён: ссылка не из разрешённых сайтов",
            )

        out[k] = url

    return out


def _get_template_or_404(template_id: str) -> Dict[str, Any]:
    db = load_templates_db()
    templates = db.get("templates") or {}
    t = templates.get(template_id)
    if not isinstance(t, dict):
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return t


def _get_template_attrs(template_id: str) -> list[dict]:
    db = load_templates_db()
    attrs_map = db.get("attributes") or {}
    attrs = attrs_map.get(template_id) or []
    if not isinstance(attrs, list):
        return []
    return [a for a in attrs if isinstance(a, dict)]


def _catalog_nodes() -> List[Dict[str, Any]]:
    try:
        from app.api.routes import catalog as catalog_routes  # lazy import

        resp = catalog_routes.list_nodes()
        nodes = resp.get("nodes", []) if isinstance(resp, dict) else []
        return nodes if isinstance(nodes, list) else []
    except Exception:
        return []


def _templates_by_category() -> Dict[str, List[str]]:
    db = load_templates_db()
    templates = db.get("templates") or {}
    out: Dict[str, List[str]] = {}
    if isinstance(templates, dict):
      for tid, tpl in templates.items():
          if not isinstance(tpl, dict):
              continue
          cid = str(tpl.get("category_id") or "").strip()
          if not cid:
              continue
          out.setdefault(cid, []).append(str(tpl.get("id") or tid))
    legacy_map = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    for cid, tids in (legacy_map or {}).items():
        if not isinstance(tids, list):
            continue
        for tid in tids:
            tid_s = str(tid or "").strip()
            if tid_s:
                out.setdefault(str(cid), []).append(tid_s)
    single_map = db.get("category_to_template") if isinstance(db.get("category_to_template"), dict) else {}
    for cid, tid in (single_map or {}).items():
        tid_s = str(tid or "").strip()
        if tid_s:
            out.setdefault(str(cid), []).append(tid_s)
    for cid, tids in out.items():
        uniq: List[str] = []
        seen: set[str] = set()
        for tid in tids:
            if tid in seen:
                continue
            seen.add(tid)
            uniq.append(tid)
        out[cid] = uniq
    return out


def _resolve_template_for_category(category_id: str) -> Tuple[Optional[str], Optional[str]]:
    cid = str(category_id or "").strip()
    if not cid:
        return None, None
    cat_map = _templates_by_category()
    nodes = _catalog_nodes()
    parent_by_id: Dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        pid = str(n.get("parent_id") or "").strip()
        if nid and pid:
            parent_by_id[nid] = pid
    cur = cid
    seen: set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        tids = cat_map.get(cur) or []
        if tids:
            return str(tids[0]), cur
        cur = parent_by_id.get(cur, "")
    return None, None


def _master_fields(template_id: str) -> list[dict]:
    attrs = _get_template_attrs(template_id)
    out = []
    for a in attrs:
        code = (a.get("code") or "").strip()
        if not code:
            continue
        out.append(
            {
                "code": code,
                "name": a.get("name"),
                "type": a.get("type"),
                "scope": a.get("scope"),
                "required": bool(a.get("required")),
            }
        )
    return out


def _template_attr_meta(template_id: str) -> Dict[str, Dict[str, str]]:
    attrs = _get_template_attrs(template_id)
    out: Dict[str, Dict[str, str]] = {}
    for a in attrs:
        if not isinstance(a, dict):
            continue
        code = str(a.get("code") or "").strip()
        if not code:
            continue
        options = a.get("options") if isinstance(a.get("options"), dict) else {}
        out[code] = {
            "type": str(a.get("type") or "").strip(),
            "dict_id": str(options.get("dict_id") or "").strip(),
        }
    return out


def _normalize_mapped_specs(
    template_id: str,
    mapped_specs: Dict[str, str],
) -> Dict[str, str]:
    attr_meta = _template_attr_meta(template_id)
    out: Dict[str, str] = {}
    for code, raw_value in (mapped_specs or {}).items():
        code_s = str(code or "").strip()
        value = str(raw_value or "").strip()
        if not code_s or not value:
            continue
        meta = attr_meta.get(code_s) or {}
        attr_type = str(meta.get("type") or "").strip().lower()
        dict_id = str(meta.get("dict_id") or "").strip()
        if dict_id and attr_type == "select":
            out[code_s] = canonicalize_dictionary_value(dict_id, value)
        else:
            out[code_s] = value
    return out


def _valid_master_codes(template_id: str) -> set[str]:
    return {f["code"] for f in _master_fields(template_id) if isinstance(f, dict) and f.get("code")}


def _normalize_mapping_full(template_id: str, mapping_in: Any) -> Dict[str, str]:
    """
    FULL режим: mapping — это финальный объект { code: "field" }.
    """
    if mapping_in is None or not isinstance(mapping_in, dict):
        raise HTTPException(status_code=400, detail="mapping must be an object")

    allowed_codes = _valid_master_codes(template_id)
    mapping: Dict[str, str] = {}

    for k, v in mapping_in.items():
        kk = str(k).strip()
        vv = str(v).strip()
        if not kk or not vv:
            continue
        # ✅ режем мусор — сохраняем только коды из шаблона
        if allowed_codes and kk not in allowed_codes:
            continue
        mapping[kk] = vv

    return mapping


def _apply_mapping_patch(template_id: str, current: Dict[str, Any], patch_in: Any) -> Dict[str, str]:
    """
    PATCH режим: patch_in — это diff:
      { code: "field" } — установить/обновить
      { code: null }    — удалить
    Никаких “стираний” остальных ключей.
    """
    if patch_in is None or not isinstance(patch_in, dict):
        raise HTTPException(status_code=400, detail="mapping must be an object")

    allowed_codes = _valid_master_codes(template_id)
    next_map: Dict[str, str] = {}
    # стартуем с текущего
    if isinstance(current, dict):
        for k, v in current.items():
            kk = str(k).strip()
            vv = str(v).strip() if v is not None else ""
            if kk and vv:
                next_map[kk] = vv

    for k, v in patch_in.items():
        kk = str(k).strip()
        if not kk:
            continue
        if allowed_codes and kk not in allowed_codes:
            # неизвестные коды игнорируем, чтобы не мусорить
            continue

        if v is None:
            # удалить ключ
            if kk in next_map:
                del next_map[kk]
            continue

        vv = str(v).strip()
        if not vv:
            # пустая строка = трактуем как удаление (на всякий)
            if kk in next_map:
                del next_map[kk]
            continue

        next_map[kk] = vv

    return next_map


def _normalize_mapping_by_site(template_id: str, mapping_in: Any) -> Dict[str, Dict[str, str]]:
    if mapping_in is None or not isinstance(mapping_in, dict):
        raise HTTPException(status_code=400, detail="mapping_by_site must be an object")
    out: Dict[str, Dict[str, str]] = {"restore": {}, "store77": {}}
    for site in ("restore", "store77"):
        cur = mapping_in.get(site)
        if isinstance(cur, dict):
            out[site] = _normalize_mapping_full(template_id, cur)
    return out


def _apply_mapping_patch_by_site(template_id: str, current: Any, patch_in: Any) -> Dict[str, Dict[str, str]]:
    if patch_in is None or not isinstance(patch_in, dict):
        raise HTTPException(status_code=400, detail="mapping_by_site must be an object")

    cur_restore = {}
    cur_store = {}
    if isinstance(current, dict):
        cur_restore = current.get("restore") if isinstance(current.get("restore"), dict) else {}
        cur_store = current.get("store77") if isinstance(current.get("store77"), dict) else {}

    next_map = {
        "restore": _apply_mapping_patch(template_id, cur_restore, patch_in.get("restore") or {}),
        "store77": _apply_mapping_patch(template_id, cur_store, patch_in.get("store77") or {}),
    }
    return next_map


def _is_configured(row: Dict[str, Any]) -> bool:
    """
    ✅ Строгий критерий "Настроен":
    - есть обе ссылки
    - и есть хотя бы 1 сопоставление для каждого сайта
    """
    links = row.get("links") or {}
    has_restore = bool((links.get("restore") or "").strip())
    has_store = bool((links.get("store77") or "").strip())
    maps = row.get("mapping_by_site") or {}
    m_restore = maps.get("restore") if isinstance(maps, dict) else {}
    m_store = maps.get("store77") if isinstance(maps, dict) else {}
    has_map_restore = isinstance(m_restore, dict) and len(m_restore) > 0
    has_map_store = isinstance(m_store, dict) and len(m_store) > 0
    return bool(has_restore and has_store and has_map_restore and has_map_store)


def _dedupe_fields(fields: Any) -> list[str]:
    if not isinstance(fields, list):
        return []
    clean: list[str] = []
    seen: set[str] = set()
    for f in fields:
        s = str(f).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        clean.append(s)
    return clean


def _ensure_row_shape(row: Any) -> Dict[str, Any]:
    if not isinstance(row, dict):
        row = {}
    return {
        "priority_site": row.get("priority_site"),
        "links": _validate_links_keep_keys(row.get("links") or {}),
        "mapping_by_site": row.get("mapping_by_site")
        if isinstance(row.get("mapping_by_site"), dict)
        else {
            "restore": dict(row.get("mapping") or {}) if isinstance(row.get("mapping"), dict) else {},
            "store77": dict(row.get("mapping") or {}) if isinstance(row.get("mapping"), dict) else {},
        },
        "updated_at": row.get("updated_at"),
    }


def _get_category_row_with_fallback(category_id: str) -> Tuple[Dict[str, Any], Optional[str], Optional[str]]:
    db = load_competitor_mapping_db()
    category_rows = db.get("categories") if isinstance(db.get("categories"), dict) else {}
    row = _ensure_row_shape((category_rows or {}).get(category_id) or {})
    template_id, source_category_id = _resolve_template_for_category(category_id)
    if any((row.get("links") or {}).values()) or any((row.get("mapping_by_site") or {}).get(site) for site in ("restore", "store77")):
        return row, template_id, source_category_id
    if template_id:
        template_rows = db.get("templates") if isinstance(db.get("templates"), dict) else {}
        legacy_row = _ensure_row_shape((template_rows or {}).get(template_id) or {})
        return legacy_row, template_id, source_category_id
    return row, template_id, source_category_id


# =========================
# API
# =========================
@router.get("/template/{template_id}")
def get_template_mapping(template_id: str) -> Dict[str, Any]:
    tpl = _get_template_or_404(template_id)

    db = load_competitor_mapping_db()
    row = (db.get("templates", {}) or {}).get(template_id) or {}
    row = _ensure_row_shape(row)

    return {
        "ok": True,
        "template_id": template_id,
        "template": {
            "id": tpl.get("id"),
            "name": tpl.get("name"),
            "category_id": tpl.get("category_id"),
        },
        "master_fields": _master_fields(template_id),
        "data": row,
    }


@router.get("/category/{category_id}")
def get_category_mapping(category_id: str) -> Dict[str, Any]:
    category_id = str(category_id or "").strip()
    if not category_id:
        raise HTTPException(status_code=400, detail="category_id required")

    row, template_id, source_category_id = _get_category_row_with_fallback(category_id)
    tpl = _get_template_or_404(template_id) if template_id else None

    return {
        "ok": True,
        "category_id": category_id,
        "template_id": template_id,
        "template_source_category_id": source_category_id,
        "template": {
            "id": tpl.get("id"),
            "name": tpl.get("name"),
            "category_id": tpl.get("category_id"),
        } if isinstance(tpl, dict) else None,
        "master_fields": _master_fields(template_id) if template_id else [],
        "data": row,
    }


@router.put("/template/{template_id}")
def save_template_mapping(template_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ MERGE update (PATCH-like semantics через PUT, чтобы фронт мог слать diff)
    payload может содержать частично:
    {
      "priority_site": "restore"|"store77"|null,         (optional)
      "links": { "restore": "...", "store77": "..." },    (optional; если пришло — перезапишем оба ключа нормализованно)
      "mapping": { "<code>": "<field>" | null }           (optional; diff, null=удалить)
    }
    """
    _ = _get_template_or_404(template_id)  # ✅ проверяем что шаблон существует

    db = load_competitor_mapping_db()
    tpl_rows = db.setdefault("templates", {})
    current_raw = tpl_rows.get(template_id) or {}
    current = _ensure_row_shape(current_raw)

    # priority_site (optional)
    if "priority_site" in payload:
        priority_site = payload.get("priority_site")
        if priority_site is not None and priority_site not in ALLOWED_SITES:
            raise HTTPException(status_code=400, detail="Invalid priority_site")
        current["priority_site"] = priority_site

    # links (optional)
    if "links" in payload:
        current["links"] = _validate_links_keep_keys(payload.get("links") or {})

    # mapping_by_site (optional) — diff apply
    if "mapping_by_site" in payload:
        patch = payload.get("mapping_by_site") or {}
        current["mapping_by_site"] = _apply_mapping_patch_by_site(
            template_id,
            current.get("mapping_by_site") or {},
            patch,
        )

    # legacy: mapping (single)
    if "mapping" in payload and "mapping_by_site" not in payload:
        patch = payload.get("mapping") or {}
        merged = _apply_mapping_patch(template_id, (current.get("mapping_by_site") or {}).get("restore") or {}, patch)
        current["mapping_by_site"] = {"restore": merged, "store77": dict(merged)}

    current["updated_at"] = now_iso()

    tpl_rows[template_id] = current
    save_competitor_mapping_db(db)

    return {"ok": True, "data": current, "configured": _is_configured(current)}


@router.put("/category/{category_id}")
def save_category_mapping(category_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    category_id = str(category_id or "").strip()
    if not category_id:
        raise HTTPException(status_code=400, detail="category_id required")

    template_id, source_category_id = _resolve_template_for_category(category_id)
    current, _, _ = _get_category_row_with_fallback(category_id)
    if "priority_site" in payload:
        priority_site = payload.get("priority_site")
        if priority_site is not None and priority_site not in ALLOWED_SITES:
            raise HTTPException(status_code=400, detail="Invalid priority_site")
        current["priority_site"] = priority_site
    if "links" in payload:
        current["links"] = _validate_links_keep_keys(payload.get("links") or {})
    if "mapping_by_site" in payload:
        if not template_id:
            raise HTTPException(status_code=400, detail="No effective template for category")
        patch = payload.get("mapping_by_site") or {}
        current["mapping_by_site"] = _apply_mapping_patch_by_site(
            template_id,
            current.get("mapping_by_site") or {},
            patch,
        )
    if "mapping" in payload and "mapping_by_site" not in payload:
        if not template_id:
            raise HTTPException(status_code=400, detail="No effective template for category")
        patch = payload.get("mapping") or {}
        merged = _apply_mapping_patch(template_id, (current.get("mapping_by_site") or {}).get("restore") or {}, patch)
        current["mapping_by_site"] = {"restore": merged, "store77": dict(merged)}
    current["updated_at"] = now_iso()

    db = load_competitor_mapping_db()
    db.setdefault("categories", {})
    db["categories"][category_id] = current
    save_competitor_mapping_db(db)

    return {
        "ok": True,
        "category_id": category_id,
        "template_id": template_id,
        "template_source_category_id": source_category_id,
        "data": current,
        "configured": _is_configured(current),
    }


@router.get("/template-flags")
def template_flags() -> Dict[str, Any]:
    """
    Для списка шаблонов: где действительно настроено — ставим галочку.
    Возвращаем map: { template_id: true }
    """
    db = load_competitor_mapping_db()
    items = db.get("templates", {}) or {}

    flags: Dict[str, bool] = {}
    for tid, row in items.items():
        if not isinstance(row, dict):
            continue
        # ✅ важно: используем strict критерий (ссылки + маппинг)
        if _is_configured(row):
            flags[str(tid)] = True

    return {"ok": True, "flags": flags}


@router.post("/competitor-fields")
async def competitor_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ Реально вытаскиваем поля конкурента (restore/store77).
    UI сможет делать mapping через dropdown.
    """
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url required")

    site = detect_site(url)
    if not site:
        raise HTTPException(status_code=400, detail="Парсинг запрещён: сайт не разрешён")

    try:
        result = await extract_competitor_fields(url, return_meta=True)
    except Exception as e:
        msg = str(e) or "EXTRACT_FAILED"
        raise HTTPException(status_code=500, detail=msg)

    fields = (result or {}).get("fields") if isinstance(result, dict) else result
    fields_meta = (result or {}).get("fields_meta") if isinstance(result, dict) else []
    return {
        "ok": True,
        "site": site,
        "fields": _dedupe_fields(fields),
        "fields_meta": fields_meta,
    }


@router.post("/competitor-fields-batch")
async def competitor_fields_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ Батч-режим: одним запросом грузим поля для обеих ссылок.
    payload:
    {
      "links": { "restore": "...", "store77": "..." }
    }
    """
    links = payload.get("links") or {}
    norm_links = _validate_links_keep_keys(links)

    async def _one(site_key: str, url: str) -> Dict[str, Any]:
        url = (url or "").strip()
        if not url:
            return {"ok": True, "site": site_key, "fields": [], "skipped": True}

        site = detect_site(url)
        if site != site_key:
            return {"ok": False, "error": "Парсинг запрещён: сайт не разрешён"}

        try:
            result = await extract_competitor_fields(url, return_meta=True)
        except Exception as e:
            msg = str(e) or "EXTRACT_FAILED"
            return {"ok": False, "error": msg}

        fields = (result or {}).get("fields") if isinstance(result, dict) else result
        fields_meta = (result or {}).get("fields_meta") if isinstance(result, dict) else []
        return {
            "ok": True,
            "site": site_key,
            "fields": _dedupe_fields(fields),
            "fields_meta": fields_meta,
            "skipped": False,
        }

    import asyncio

    res = await asyncio.gather(
        _one("restore", norm_links.get("restore", "")),
        _one("store77", norm_links.get("store77", "")),
        return_exceptions=True,
    )

    def _unwrap(item: Any) -> Dict[str, Any]:
        if isinstance(item, Exception):
            return {"ok": False, "error": "EXTRACT_FAILED"}
        if isinstance(item, dict):
            return item
        return {"ok": False, "error": "EXTRACT_FAILED"}

    r_restore = _unwrap(res[0] if len(res) > 0 else Exception("missing"))
    r_store77 = _unwrap(res[1] if len(res) > 1 else Exception("missing"))

    return {"ok": True, "results": {"restore": r_restore, "store77": r_store77}}


@router.post("/competitor-content-batch")
async def competitor_content_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Загружает контент (specs + media + description) для двух ссылок.
    payload:
    {
      "links": { "restore": "...", "store77": "..." }
    }
    """
    template_id = payload.get("template_id")
    mapping_by_site: Dict[str, Dict[str, str]] = {"restore": {}, "store77": {}}
    if isinstance(template_id, str) and template_id:
        db = load_competitor_mapping_db()
        row = (db.get("templates", {}) or {}).get(template_id) or {}
        row = _ensure_row_shape(row)
        mapping_by_site = row.get("mapping_by_site") or {"restore": {}, "store77": {}}

    def _norm_key(v: str) -> str:
        return " ".join(str(v or "").split()).lower()

    def _map_specs(specs: Dict[str, str], mapping: Dict[str, str]) -> Dict[str, str]:
        if not specs or not mapping:
            return {}
        norm_specs = {_norm_key(k): v for k, v in specs.items() if k}
        out: Dict[str, str] = {}
        for code, field in (mapping or {}).items():
            field_key = _norm_key(field)
            if not field_key:
                continue
            out[code] = norm_specs.get(field_key, "")
        return out

    links = payload.get("links") or {}
    norm_links = _validate_links_keep_keys(links)

    async def _one(site_key: str, url: str) -> Dict[str, Any]:
        url = (url or "").strip()
        if not url:
            return {"ok": True, "site": site_key, "images": [], "specs": {}, "description": "", "skipped": True}

        site = detect_site(url)
        if site != site_key:
            return {"ok": False, "error": "Парсинг запрещён: сайт не разрешён"}

        try:
            result = await extract_competitor_content(url)
        except Exception as e:
            msg = str(e) or "EXTRACT_FAILED"
            return {"ok": False, "error": msg}

        specs = result.get("specs") or {}
        mapped_specs_raw = _map_specs(specs, mapping_by_site.get(site_key, {}) or {})
        return {
            "ok": True,
            "site": site_key,
            "images": result.get("images") or [],
            "specs": specs,
            "mapped_specs_raw": mapped_specs_raw,
            "mapped_specs": _normalize_mapped_specs(template_id, mapped_specs_raw) if template_id else mapped_specs_raw,
            "description": result.get("description") or "",
            "skipped": False,
        }

    import asyncio

    res = await asyncio.gather(
        _one("restore", norm_links.get("restore", "")),
        _one("store77", norm_links.get("store77", "")),
        return_exceptions=True,
    )

    def _unwrap(item: Any) -> Dict[str, Any]:
        if isinstance(item, Exception):
            return {"ok": False, "error": "EXTRACT_FAILED"}
        if isinstance(item, dict):
            return item
        return {"ok": False, "error": "EXTRACT_FAILED"}

    r_restore = _unwrap(res[0] if len(res) > 0 else Exception("missing"))
    r_store77 = _unwrap(res[1] if len(res) > 1 else Exception("missing"))

    return {"ok": True, "results": {"restore": r_restore, "store77": r_store77}}
