from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.json_store import read_doc, write_doc, with_lock
from app.api.routes import marketplace_mapping, yandex_market, ozon_market, comfyui

router = APIRouter(prefix="/connectors/status", tags=["connectors-status"])

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
DATA_DIR = BASE_DIR / "data" / "marketplaces"
STATE_PATH = DATA_DIR / "connectors_scheduler.json"

SCHEDULE_SECONDS: Dict[str, int] = {
    "5m": 5 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "2h": 2 * 60 * 60,
    "6h": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
}

SCHEDULE_LABELS: Dict[str, str] = {
    "5m": "каждые 5 минут",
    "30m": "каждые 30 минут",
    "1h": "каждый час",
    "2h": "каждые 2 часа",
    "6h": "каждые 6 часов",
    "12h": "каждые 12 часов",
    "24h": "раз в сутки",
    "7d": "раз в неделю",
}

DEFAULT_SCHEDULE = "1h"

PROVIDERS_DEF: Dict[str, Dict[str, Any]] = {
    "yandex_market": {
        "title": "Я.Маркет",
        "methods": {
            "categories_tree": "Импорт дерева категорий",
            "category_parameters": "Импорт характеристик категорий",
            "offer_cards_import": "Импорт контента товаров",
        },
    },
    "ozon": {
        "title": "OZON",
        "methods": {
            "categories_tree": "Импорт дерева категорий",
            "category_attributes": "Импорт характеристик категорий",
            "product_content_status": "Импорт статуса и рейтинга товаров",
        },
    },
    "comfyui": {
        "title": "ComfyUI",
        "methods": {
            "healthcheck": "Проверка доступности генератора",
        },
    },
}

_runner_task: Optional[asyncio.Task] = None
_runner_lock = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: Any) -> Optional[datetime]:
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _severity(fail_count: int) -> str:
    if fail_count <= 0:
        return "ok"
    if fail_count <= 2:
        return "warn"
    return "critical"


def _default_state() -> Dict[str, Any]:
    providers: Dict[str, Any] = {}
    for pcode, pdef in PROVIDERS_DEF.items():
        methods: Dict[str, Any] = {}
        for mcode in pdef["methods"].keys():
            methods[mcode] = {
                "schedule": DEFAULT_SCHEDULE,
                "last_run_at": None,
                "last_success_at": None,
                "last_error_at": None,
                "last_error": "",
                "fail_count": 0,
                "status": "ok",
            }
        settings: Dict[str, Any] = {}
        if pcode == "yandex_market":
            settings["offer_id_source"] = "sku_gt"
        providers[pcode] = {"methods": methods, "settings": settings, "import_stores": []}
    return {"version": 1, "updated_at": None, "providers": providers}


def _load_state() -> Dict[str, Any]:
    doc = read_doc(STATE_PATH, default=_default_state())
    if not isinstance(doc, dict):
        doc = _default_state()
    if not isinstance(doc.get("providers"), dict):
        doc["providers"] = {}
    for pcode, pdef in PROVIDERS_DEF.items():
        prow = doc["providers"].get(pcode)
        if not isinstance(prow, dict):
            prow = {"methods": {}, "settings": {}}
        methods = prow.get("methods") if isinstance(prow.get("methods"), dict) else {}
        settings = prow.get("settings") if isinstance(prow.get("settings"), dict) else {}
        import_stores = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []
        for mcode in pdef["methods"].keys():
            mrow = methods.get(mcode)
            if not isinstance(mrow, dict):
                mrow = {}
            schedule = str(mrow.get("schedule") or DEFAULT_SCHEDULE)
            if schedule not in SCHEDULE_SECONDS:
                schedule = DEFAULT_SCHEDULE
            fail_count = int(mrow.get("fail_count") or 0)
            methods[mcode] = {
                "schedule": schedule,
                "last_run_at": mrow.get("last_run_at"),
                "last_success_at": mrow.get("last_success_at"),
                "last_error_at": mrow.get("last_error_at"),
                "last_error": str(mrow.get("last_error") or ""),
                "fail_count": fail_count,
                "status": str(mrow.get("status") or _severity(fail_count)),
            }
        prow["methods"] = methods
        if pcode == "yandex_market":
            settings["offer_id_source"] = "sku_gt"
            normalized_stores: List[Dict[str, Any]] = []
            for raw in import_stores:
                if not isinstance(raw, dict):
                    continue
                store_id = str(raw.get("id") or "").strip() or f"ym_store_{uuid4().hex[:8]}"
                business_id = str(raw.get("business_id") or "").strip()
                title = str(raw.get("title") or business_id or store_id).strip()
                if not business_id:
                    continue
                auth_mode = _normalize_store_auth_mode(raw.get("auth_mode"))
                normalized_stores.append(
                    {
                        "id": store_id,
                        "title": title,
                        "business_id": business_id,
                        "token": str(raw.get("token") or "").strip(),
                        "auth_mode": auth_mode,
                        "enabled": bool(raw.get("enabled", True)),
                        "notes": str(raw.get("notes") or "").strip(),
                        "last_check_at": raw.get("last_check_at"),
                        "last_check_status": str(raw.get("last_check_status") or "").strip() or "idle",
                        "last_check_error": str(raw.get("last_check_error") or "").strip(),
                        "created_at": raw.get("created_at") or _now_iso(),
                        "updated_at": raw.get("updated_at") or _now_iso(),
                    }
                )
            prow["import_stores"] = normalized_stores
        elif pcode == "ozon":
            normalized_stores: List[Dict[str, Any]] = []
            for raw in import_stores:
                if not isinstance(raw, dict):
                    continue
                store_id = str(raw.get("id") or "").strip() or f"ozon_store_{uuid4().hex[:8]}"
                client_id = str(raw.get("client_id") or "").strip()
                api_key = str(raw.get("api_key") or raw.get("token") or "").strip()
                title = str(raw.get("title") or client_id or store_id).strip()
                if not client_id or not api_key:
                    continue
                normalized_stores.append(
                    {
                        "id": store_id,
                        "title": title,
                        "client_id": client_id,
                        "api_key": api_key,
                        "enabled": bool(raw.get("enabled", True)),
                        "notes": str(raw.get("notes") or "").strip(),
                        "last_check_at": raw.get("last_check_at"),
                        "last_check_status": str(raw.get("last_check_status") or "").strip() or "idle",
                        "last_check_error": str(raw.get("last_check_error") or "").strip(),
                        "created_at": raw.get("created_at") or _now_iso(),
                        "updated_at": raw.get("updated_at") or _now_iso(),
                    }
                )
            prow["import_stores"] = normalized_stores
        prow["settings"] = settings
        doc["providers"][pcode] = prow
    return doc


def _save_state(doc: Dict[str, Any]) -> None:
    doc["updated_at"] = _now_iso()
    write_doc(STATE_PATH, doc)


def _next_run_at(method_row: Dict[str, Any]) -> Optional[str]:
    schedule = str(method_row.get("schedule") or DEFAULT_SCHEDULE)
    interval = SCHEDULE_SECONDS.get(schedule, SCHEDULE_SECONDS[DEFAULT_SCHEDULE])
    base = _parse_iso(method_row.get("last_run_at"))
    if not base:
        return _now_iso()
    return (base + timedelta(seconds=interval)).isoformat()


def _mapped_provider_category_ids(provider_code: str) -> List[str]:
    items = marketplace_mapping._load_mappings()  # noqa: SLF001 - local backend utility usage
    out: List[str] = []
    for row in items.values():
        if not isinstance(row, dict):
            continue
        pid = str(row.get(provider_code) or "").strip()
        if pid:
            out.append(pid)
    return sorted(set(out))


def _first_enabled_yandex_store() -> Dict[str, Any]:
    state = _load_state()
    prow = state.get("providers", {}).get("yandex_market", {})
    stores = prow.get("import_stores") if isinstance(prow, dict) else []
    if isinstance(stores, list):
        for store in stores:
            if not isinstance(store, dict):
                continue
            if not bool(store.get("enabled")):
                continue
            if str(store.get("business_id") or "").strip():
                return store
    return {}


def _first_enabled_ozon_store() -> Dict[str, Any]:
    state = _load_state()
    prow = state.get("providers", {}).get("ozon", {})
    stores = prow.get("import_stores") if isinstance(prow, dict) else []
    if isinstance(stores, list):
        for store in stores:
            if not isinstance(store, dict):
                continue
            if not bool(store.get("enabled")):
                continue
            if str(store.get("client_id") or "").strip() and str(store.get("api_key") or "").strip():
                return store
    return {}


def _normalize_store_auth_mode(value: Any) -> str:
    mode = str(value or "").strip().lower() or "auto"
    return mode if mode in {"auto", "api-key", "oauth", "bearer"} else "auto"


async def _run_yandex_categories_tree() -> None:
    store = _first_enabled_yandex_store()
    req = yandex_market.ImportCategoriesReq(
        language="RU",
        token=str(store.get("token") or "").strip() or None,
        auth_mode=str(store.get("auth_mode") or "").strip() or None,
    )
    await yandex_market.import_categories_tree(req)


async def _run_yandex_category_parameters() -> None:
    ids = _mapped_provider_category_ids("yandex_market")
    store = _first_enabled_yandex_store()
    for cid in ids:
        req = yandex_market.ImportCategoryParamsReq(
            category_id=cid,
            language="RU",
            token=str(store.get("token") or "").strip() or None,
            auth_mode=str(store.get("auth_mode") or "").strip() or None,
        )
        await yandex_market.import_category_parameters(req)


async def _run_yandex_offer_cards_import() -> None:
    state = _load_state()
    prow = state.get("providers", {}).get("yandex_market", {})
    stores = prow.get("import_stores") if isinstance(prow, dict) else []
    enabled_stores = [x for x in (stores or []) if isinstance(x, dict) and bool(x.get("enabled")) and str(x.get("business_id") or "").strip()]
    if not enabled_stores:
        raise HTTPException(status_code=400, detail="YANDEX_IMPORT_STORES_MISSING")
    for store in enabled_stores:
        req = yandex_market.OfferCardsSyncReq(
            business_id=str(store.get("business_id") or "").strip(),
            token=str(store.get("token") or "").strip() or None,
            auth_mode=str(store.get("auth_mode") or "").strip() or None,
            store_id=str(store.get("id") or "").strip() or None,
            store_title=str(store.get("title") or "").strip() or None,
            include_descendants=True,
            with_recommendations=True,
            apply_to_products=True,
            overwrite_existing=False,
            limit=20000,
        )
        await yandex_market.sync_offer_cards(req)


async def _run_ozon_categories_tree() -> None:
    store = _first_enabled_ozon_store()
    req = ozon_market.ImportCategoriesReq(
        language="DEFAULT",
        token=str(store.get("api_key") or "").strip() or None,
        client_id=str(store.get("client_id") or "").strip() or None,
    )
    await ozon_market.import_categories_tree(req)


async def _run_ozon_category_attributes() -> None:
    ids = _mapped_provider_category_ids("ozon")
    store = _first_enabled_ozon_store()
    for cid in ids:
        req = ozon_market.ImportCategoryAttrsReq(
            category_id=cid,
            language="DEFAULT",
            token=str(store.get("api_key") or "").strip() or None,
            client_id=str(store.get("client_id") or "").strip() or None,
        )
        await ozon_market.import_category_attributes(req)


async def _run_ozon_product_content_status() -> None:
    state = _load_state()
    prow = state.get("providers", {}).get("ozon", {})
    stores = prow.get("import_stores") if isinstance(prow, dict) else []
    enabled_stores = [x for x in (stores or []) if isinstance(x, dict) and bool(x.get("enabled")) and str(x.get("client_id") or "").strip() and str(x.get("api_key") or "").strip()]
    if not enabled_stores:
        raise HTTPException(status_code=400, detail="OZON_IMPORT_STORES_MISSING")
    for store in enabled_stores:
        req = ozon_market.OzonProductsSyncReq(
            client_id=str(store.get("client_id") or "").strip(),
            token=str(store.get("api_key") or "").strip(),
            store_id=str(store.get("id") or "").strip() or None,
            store_title=str(store.get("title") or "").strip() or None,
            include_descendants=True,
            limit=20000,
        )
        await ozon_market.sync_product_statuses(req)


async def _run_comfyui_healthcheck() -> None:
    await comfyui.comfyui_status()


METHOD_RUNNERS: Dict[Tuple[str, str], Callable[[], Awaitable[None]]] = {
    ("yandex_market", "categories_tree"): _run_yandex_categories_tree,
    ("yandex_market", "category_parameters"): _run_yandex_category_parameters,
    ("yandex_market", "offer_cards_import"): _run_yandex_offer_cards_import,
    ("ozon", "categories_tree"): _run_ozon_categories_tree,
    ("ozon", "category_attributes"): _run_ozon_category_attributes,
    ("ozon", "product_content_status"): _run_ozon_product_content_status,
    ("comfyui", "healthcheck"): _run_comfyui_healthcheck,
}


async def _run_method(provider: str, method: str) -> None:
    fn = METHOD_RUNNERS.get((provider, method))
    if fn is None:
        raise HTTPException(status_code=404, detail="METHOD_NOT_FOUND")

    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
    finally:
        lock.release()

    prow = state["providers"][provider]
    mrow = prow["methods"][method]
    mrow["last_run_at"] = _now_iso()

    try:
        await fn()
        mrow["last_success_at"] = _now_iso()
        mrow["last_error"] = ""
        mrow["fail_count"] = 0
        mrow["status"] = "ok"
    except Exception as e:
        mrow["last_error_at"] = _now_iso()
        mrow["last_error"] = str(e)
        mrow["fail_count"] = int(mrow.get("fail_count") or 0) + 1
        mrow["status"] = _severity(mrow["fail_count"])
        raise
    finally:
        lock = with_lock("connectors_scheduler_state")
        lock.acquire()
        try:
            _save_state(state)
        finally:
            lock.release()


async def _run_provider(provider: str) -> Dict[str, Any]:
    if provider not in PROVIDERS_DEF:
        raise HTTPException(status_code=404, detail="PROVIDER_NOT_FOUND")
    methods = list(PROVIDERS_DEF[provider]["methods"].keys())
    results: List[Dict[str, Any]] = []
    for m in methods:
        try:
            await _run_method(provider, m)
            results.append({"method": m, "ok": True})
        except Exception as e:
            results.append({"method": m, "ok": False, "error": str(e)})
    return {"provider": provider, "results": results}


def _state_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    providers_out: List[Dict[str, Any]] = []
    for pcode, pdef in PROVIDERS_DEF.items():
        prow = state.get("providers", {}).get(pcode, {})
        methods = prow.get("methods", {}) if isinstance(prow, dict) else {}
        methods_out: List[Dict[str, Any]] = []
        for mcode, mtitle in pdef["methods"].items():
            mrow = methods.get(mcode, {})
            if not isinstance(mrow, dict):
                mrow = {}
            schedule = str(mrow.get("schedule") or DEFAULT_SCHEDULE)
            if schedule not in SCHEDULE_SECONDS:
                schedule = DEFAULT_SCHEDULE
            last_run = mrow.get("last_run_at")
            base = _parse_iso(last_run)
            next_run = None
            if base:
                next_run = (base + timedelta(seconds=SCHEDULE_SECONDS[schedule])).isoformat()
            methods_out.append(
                {
                    "code": mcode,
                    "title": mtitle,
                    "schedule": schedule,
                    "schedule_label": SCHEDULE_LABELS[schedule],
                    "last_run_at": mrow.get("last_run_at"),
                    "last_success_at": mrow.get("last_success_at"),
                    "last_error_at": mrow.get("last_error_at"),
                    "last_error": mrow.get("last_error") or "",
                    "status": mrow.get("status") or "ok",
                    "next_run_at": next_run,
                }
            )
        providers_out.append({"code": pcode, "title": pdef["title"], "methods": methods_out})
        providers_out[-1]["settings"] = prow.get("settings") if isinstance(prow.get("settings"), dict) else {}
        providers_out[-1]["import_stores"] = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []
    options = [{"code": code, "label": label} for code, label in SCHEDULE_LABELS.items()]
    provider_setting_options = {
        "yandex_market": {
            "offer_id_source": [
                {"code": "sku_gt", "label": "SKU GT"},
            ]
        }
    }
    return {"ok": True, "providers": providers_out, "schedule_options": options, "provider_setting_options": provider_setting_options}


class UpdateScheduleReq(BaseModel):
    provider: str = Field(min_length=1)
    method: str = Field(min_length=1)
    schedule: str = Field(min_length=1)


class UpdateProviderSettingsReq(BaseModel):
    provider: str = Field(min_length=1)
    settings: Dict[str, Any] = Field(default_factory=dict)


class ImportStoreReq(BaseModel):
    provider: str = Field(min_length=1)
    title: str = Field(min_length=1)
    business_id: Optional[str] = None
    client_id: Optional[str] = None
    api_key: Optional[str] = None
    token: Optional[str] = None
    auth_mode: Optional[str] = None
    enabled: bool = True
    notes: Optional[str] = None


@router.get("")
def connectors_status() -> Dict[str, Any]:
    state = _load_state()
    return _state_payload(state)


@router.put("/schedule")
def connectors_update_schedule(req: UpdateScheduleReq) -> Dict[str, Any]:
    provider = str(req.provider or "").strip()
    method = str(req.method or "").strip()
    schedule = str(req.schedule or "").strip()
    if schedule not in SCHEDULE_SECONDS:
        raise HTTPException(status_code=400, detail="SCHEDULE_INVALID")
    if provider not in PROVIDERS_DEF:
        raise HTTPException(status_code=404, detail="PROVIDER_NOT_FOUND")
    if method not in PROVIDERS_DEF[provider]["methods"]:
        raise HTTPException(status_code=404, detail="METHOD_NOT_FOUND")

    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
        state["providers"][provider]["methods"][method]["schedule"] = schedule
        _save_state(state)
    finally:
        lock.release()

    return _state_payload(state)


@router.put("/provider-settings")
def connectors_update_provider_settings(req: UpdateProviderSettingsReq) -> Dict[str, Any]:
    provider = str(req.provider or "").strip()
    if provider not in PROVIDERS_DEF:
        raise HTTPException(status_code=404, detail="PROVIDER_NOT_FOUND")

    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
        prow = state["providers"].setdefault(provider, {"methods": {}, "settings": {}})
        settings = prow.get("settings") if isinstance(prow.get("settings"), dict) else {}
        if provider == "yandex_market":
            settings["offer_id_source"] = "sku_gt"
        prow["settings"] = settings
        state["providers"][provider] = prow
        _save_state(state)
    finally:
        lock.release()

    return _state_payload(state)


@router.post("/import-stores")
def connectors_create_import_store(req: ImportStoreReq) -> Dict[str, Any]:
    provider = str(req.provider or "").strip()
    if provider not in {"yandex_market", "ozon"}:
        raise HTTPException(status_code=400, detail="IMPORT_STORES_UNSUPPORTED_PROVIDER")

    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
        prow = state["providers"].setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
        stores = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []
        now = _now_iso()
        if provider == "yandex_market":
            business_id = str(req.business_id or "").strip()
            if not business_id:
                raise HTTPException(status_code=400, detail="YANDEX_BUSINESS_ID_REQUIRED")
            if any(str(x.get("business_id") or "").strip() == business_id for x in stores if isinstance(x, dict)):
                raise HTTPException(status_code=400, detail="YANDEX_IMPORT_STORE_ALREADY_EXISTS")
            stores.append(
                {
                    "id": f"ym_store_{uuid4().hex[:8]}",
                    "title": str(req.title or "").strip(),
                    "business_id": business_id,
                    "token": str(req.token or "").strip(),
                    "auth_mode": _normalize_store_auth_mode(req.auth_mode),
                    "enabled": bool(req.enabled),
                    "notes": str(req.notes or "").strip(),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        else:
            client_id = str(req.client_id or "").strip()
            api_key = str(req.api_key or req.token or "").strip()
            if not client_id:
                raise HTTPException(status_code=400, detail="OZON_CLIENT_ID_REQUIRED")
            if not api_key:
                raise HTTPException(status_code=400, detail="OZON_API_KEY_REQUIRED")
            if any(str(x.get("client_id") or "").strip() == client_id for x in stores if isinstance(x, dict)):
                raise HTTPException(status_code=400, detail="OZON_IMPORT_STORE_ALREADY_EXISTS")
            stores.append(
                {
                    "id": f"ozon_store_{uuid4().hex[:8]}",
                    "title": str(req.title or "").strip(),
                    "client_id": client_id,
                    "api_key": api_key,
                    "enabled": bool(req.enabled),
                    "notes": str(req.notes or "").strip(),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        prow["import_stores"] = stores
        state["providers"][provider] = prow
        _save_state(state)
    finally:
        lock.release()
    return _state_payload(state)


@router.put("/import-stores/{provider}/{store_id}")
def connectors_update_import_store(provider: str, store_id: str, req: ImportStoreReq) -> Dict[str, Any]:
    provider = str(provider or "").strip()
    if provider not in {"yandex_market", "ozon"}:
        raise HTTPException(status_code=400, detail="IMPORT_STORES_UNSUPPORTED_PROVIDER")

    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
        prow = state["providers"].setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
        stores = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []
        target = None
        for store in stores:
            if isinstance(store, dict) and str(store.get("id") or "").strip() == str(store_id or "").strip():
                target = store
                break
        if target is None:
            raise HTTPException(status_code=404, detail="IMPORT_STORE_NOT_FOUND")
        target["title"] = str(req.title or "").strip()
        if provider == "yandex_market":
            business_id = str(req.business_id or "").strip()
            if not business_id:
                raise HTTPException(status_code=400, detail="YANDEX_BUSINESS_ID_REQUIRED")
            if any(
                str(x.get("business_id") or "").strip() == business_id and str(x.get("id") or "").strip() != str(store_id or "").strip()
                for x in stores if isinstance(x, dict)
            ):
                raise HTTPException(status_code=400, detail="YANDEX_IMPORT_STORE_ALREADY_EXISTS")
            target["business_id"] = business_id
            target["token"] = str(req.token or "").strip()
            target["auth_mode"] = _normalize_store_auth_mode(req.auth_mode)
        else:
            client_id = str(req.client_id or "").strip()
            api_key = str(req.api_key or req.token or "").strip()
            if not client_id:
                raise HTTPException(status_code=400, detail="OZON_CLIENT_ID_REQUIRED")
            if not api_key:
                raise HTTPException(status_code=400, detail="OZON_API_KEY_REQUIRED")
            if any(
                str(x.get("client_id") or "").strip() == client_id and str(x.get("id") or "").strip() != str(store_id or "").strip()
                for x in stores if isinstance(x, dict)
            ):
                raise HTTPException(status_code=400, detail="OZON_IMPORT_STORE_ALREADY_EXISTS")
            target["client_id"] = client_id
            target["api_key"] = api_key
        target["enabled"] = bool(req.enabled)
        target["notes"] = str(req.notes or "").strip()
        target["updated_at"] = _now_iso()
        prow["import_stores"] = stores
        state["providers"][provider] = prow
        _save_state(state)
    finally:
        lock.release()
    return _state_payload(state)


@router.delete("/import-stores/{provider}/{store_id}")
def connectors_delete_import_store(provider: str, store_id: str) -> Dict[str, Any]:
    provider = str(provider or "").strip()
    if provider not in {"yandex_market", "ozon"}:
        raise HTTPException(status_code=400, detail="IMPORT_STORES_UNSUPPORTED_PROVIDER")

    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
        prow = state["providers"].setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
        stores = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []
        next_stores = [x for x in stores if not (isinstance(x, dict) and str(x.get("id") or "").strip() == str(store_id or "").strip())]
        prow["import_stores"] = next_stores
        state["providers"][provider] = prow
        _save_state(state)
    finally:
        lock.release()
    return _state_payload(state)


@router.post("/import-stores/{provider}/{store_id}/check")
async def connectors_check_import_store(provider: str, store_id: str) -> Dict[str, Any]:
    provider = str(provider or "").strip()
    if provider not in {"yandex_market", "ozon"}:
        raise HTTPException(status_code=400, detail="IMPORT_STORES_UNSUPPORTED_PROVIDER")

    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
        prow = state["providers"].setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
        stores = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []
        target = None
        for store in stores:
            if isinstance(store, dict) and str(store.get("id") or "").strip() == str(store_id or "").strip():
                target = store
                break
        if target is None:
            raise HTTPException(status_code=404, detail="IMPORT_STORE_NOT_FOUND")
    finally:
        lock.release()

    ok = False
    error_text = ""
    detected_auth_mode = _normalize_store_auth_mode(target.get("auth_mode"))
    try:
        if provider == "yandex_market":
            probe = await yandex_market.probe_store_access(
                token=str(target.get("token") or "").strip(),
                business_id=str(target.get("business_id") or "").strip(),
                auth_mode=detected_auth_mode,
            )
            ok = bool(probe.get("ok"))
            detected_auth_mode = str(probe.get("auth_mode") or detected_auth_mode)
        else:
            probe = await ozon_market.probe_store_access(
                api_key=str(target.get("api_key") or "").strip(),
                client_id=str(target.get("client_id") or "").strip(),
            )
            ok = bool(probe.get("ok"))
            detected_auth_mode = "api-key"
    except HTTPException as e:
        error_text = str(e.detail or "").strip()
    except Exception as e:
        error_text = str(e)

    checked_at = _now_iso()
    lock = with_lock("connectors_scheduler_state")
    lock.acquire()
    try:
        state = _load_state()
        prow = state["providers"].setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
        stores = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []
        for store in stores:
            if isinstance(store, dict) and str(store.get("id") or "").strip() == str(store_id or "").strip():
                store["last_check_at"] = checked_at
                store["last_check_status"] = "ok" if ok else "error"
                store["last_check_error"] = "" if ok else error_text
                if ok and detected_auth_mode in {"api-key", "oauth", "bearer"}:
                    store["auth_mode"] = detected_auth_mode
                store["updated_at"] = checked_at
                break
        prow["import_stores"] = stores
        state["providers"][provider] = prow
        _save_state(state)
    finally:
        lock.release()

    return {
        "ok": ok,
        "provider": provider,
        "store_id": store_id,
        "checked_at": checked_at,
        "auth_mode": detected_auth_mode,
        "error": error_text,
        "state": _state_payload(_load_state()),
    }


@router.post("/run/{provider}")
async def connectors_run_provider(provider: str) -> Dict[str, Any]:
    async with _runner_lock:
        result = await _run_provider(str(provider or "").strip())
    state = _load_state()
    return {"ok": True, "run": result, "state": _state_payload(state)}


async def _scheduler_loop() -> None:
    while True:
        await asyncio.sleep(30)
        state = _load_state()
        now = datetime.now(timezone.utc)
        due: List[Tuple[str, str]] = []
        for pcode, pdef in PROVIDERS_DEF.items():
            methods = state.get("providers", {}).get(pcode, {}).get("methods", {})
            for mcode in pdef["methods"].keys():
                mrow = methods.get(mcode, {})
                schedule = str(mrow.get("schedule") or DEFAULT_SCHEDULE)
                interval = SCHEDULE_SECONDS.get(schedule, SCHEDULE_SECONDS[DEFAULT_SCHEDULE])
                last = _parse_iso(mrow.get("last_run_at"))
                if last is None:
                    due.append((pcode, mcode))
                    continue
                if (now - last).total_seconds() >= interval:
                    due.append((pcode, mcode))

        if not due:
            continue
        async with _runner_lock:
            for pcode, mcode in due:
                try:
                    await _run_method(pcode, mcode)
                except Exception:
                    # state already updated in _run_method
                    continue


def start_scheduler() -> None:
    global _runner_task
    if _runner_task is None or _runner_task.done():
        _runner_task = asyncio.create_task(_scheduler_loop())


async def stop_scheduler() -> None:
    global _runner_task
    if _runner_task is None:
        return
    _runner_task.cancel()
    try:
        await _runner_task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    _runner_task = None
