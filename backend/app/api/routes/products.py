from __future__ import annotations

import os
import time
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from app.core.products.service import (
    create_product_service,
    get_product_service,
    get_products_bulk_service,
    patch_product_service,  # ✅ вместо update_product
    list_products_by_category_service,
    find_product_by_sku_service,
    allocate_sku_pairs_service,
)
from app.core.products.repo import load_products as load_products_repo
from app.core.json_store import JsonStoreError, read_doc, DATA_DIR
from app.core.object_storage import ObjectStorageError, delete_object, s3_enabled, upload_bytes
from app.storage.json_store import load_dictionaries_db, load_templates_db
from app.storage.relational_pim_store import load_catalog_nodes

router = APIRouter(prefix="/products", tags=["products"])

YANDEX_OFFER_CARDS_PATH = DATA_DIR / "marketplaces" / "yandex_market" / "offer_cards_content.json"
CONNECTORS_STATE_PATH = DATA_DIR / "marketplaces" / "connectors_scheduler.json"
OZON_PRODUCT_RATING_PATH = DATA_DIR / "marketplaces" / "ozon" / "product_rating_by_sku.json"
OZON_IMPORT_INFO_PATH = DATA_DIR / "marketplaces" / "ozon" / "import_products_info.json"
_PRODUCT_NEW_BOOTSTRAP_CACHE_TTL_SECONDS = 300.0
_product_new_bootstrap_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}


def _load_catalog_nodes_doc() -> List[Dict[str, Any]]:
    return load_catalog_nodes()


def _product_new_bootstrap_payload() -> Dict[str, Any]:
    now = time.time()
    cached = _product_new_bootstrap_cache.get("payload")
    cached_ts = float(_product_new_bootstrap_cache.get("ts") or 0.0)
    if cached and now - cached_ts < _PRODUCT_NEW_BOOTSTRAP_CACHE_TTL_SECONDS:
        return cached

    catalog_nodes = _load_catalog_nodes_doc()
    templates_db = load_templates_db()
    template_tree = []
    for node in catalog_nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or "").strip()
        if not nid:
            continue
        template_ids = (templates_db.get("category_to_templates") or {}).get(nid, []) if isinstance(templates_db.get("category_to_templates"), dict) else []
        template_id = template_ids[0] if isinstance(template_ids, list) and template_ids else (templates_db.get("category_to_template") or {}).get(nid) if isinstance(templates_db.get("category_to_template"), dict) else None
        template_tree.append({
            "id": nid,
            "parent_id": node.get("parent_id"),
            "template_id": template_id,
        })

    dict_db = load_dictionaries_db()
    attributes = []
    dictionaries = []
    for row in dict_db.get("items", []) or []:
        if not isinstance(row, dict):
            continue
        dict_id = str(row.get("id") or "").strip()
        if not dict_id:
            continue
        title = str(row.get("title") or dict_id).strip() or dict_id
        code = str(row.get("code") or "").strip()
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        attributes.append({
            "id": row.get("attr_id") or dict_id,
            "title": title,
            "code": code,
            "type": row.get("type"),
            "scope": row.get("scope"),
            "dict_id": dict_id,
        })
        dictionaries.append({
            "id": dict_id,
            "title": title,
            "code": code,
            "meta": {"service": bool(meta.get("service"))},
        })

    payload = {
        "catalog_nodes": catalog_nodes,
        "template_tree": template_tree,
        "attributes": attributes,
        "dictionaries": dictionaries,
    }
    _product_new_bootstrap_cache["ts"] = now
    _product_new_bootstrap_cache["payload"] = payload
    return payload


class CreateProductReq(BaseModel):
    category_id: str
    type: str = Field(default="single")  # single|multi
    title: str
    sku_pim: Optional[str] = None
    sku_gt: Optional[str] = None
    group_id: Optional[str] = None
    selected_params: List[str] = Field(default_factory=list)
    feature_params: List[str] = Field(default_factory=list)
    exports_enabled: Dict[str, bool] = Field(default_factory=dict)


class PatchProductReq(BaseModel):
    category_id: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    title: Optional[str] = None
    sku_pim: Optional[str] = None
    sku_gt: Optional[str] = None
    group_id: Optional[str] = None
    selected_params: Optional[List[str]] = None
    feature_params: Optional[List[str]] = None
    exports_enabled: Optional[Dict[str, bool]] = None
    content: Optional[Dict[str, Any]] = None


def _http_from_store_error(code: str) -> HTTPException:
    if code in ("PRODUCT_NOT_FOUND",):
        return HTTPException(status_code=404, detail=code)
    if code in ("DUPLICATE_SKU_GT",):
        return HTTPException(status_code=409, detail=code)
    if code in ("CATEGORY_REQUIRED", "TITLE_REQUIRED", "BAD_TYPE", "BAD_STATUS", "BAD_SKU"):
        return HTTPException(status_code=400, detail=code)
    return HTTPException(status_code=400, detail=code)


def _offer_ids_for_product(product: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in ("sku_gt",):
        value = str(product.get(key) or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _normalize_market_status(value: str) -> str:
    raw = str(value or "").strip().upper()
    mapping = {
        "HAS_CARD_CAN_UPDATE": "Карточка есть",
        "HAS_CARD_CAN_UPDATE_PROCESSING": "Обновляется",
        "HAS_CARD": "Карточка есть",
        "NO_CARD": "Нет карточки",
        "REJECTED": "Отклонено",
    }
    return mapping.get(raw, raw or "Нет данных")


def _normalize_ozon_status(value: str) -> str:
    raw = str(value or "").strip().upper()
    mapping = {
        "IMPORTING": "Импортируется",
        "IMPORTED": "Импортирован",
        "FAILED": "Ошибка импорта",
        "MODERATING": "На модерации",
        "PUBLISHED": "Опубликован",
        "PROCESSING": "Обрабатывается",
    }
    return mapping.get(raw, raw or "Нет данных")


def _load_ozon_summary(product: Dict[str, Any]) -> Dict[str, Any]:
    state = _load_connectors_state()
    providers = state.get("providers") if isinstance(state, dict) else {}
    if not isinstance(providers, dict):
        providers = {}
    ozon_provider = providers.get("ozon") if isinstance(providers.get("ozon"), dict) else {}
    stores = ozon_provider.get("import_stores") if isinstance(ozon_provider.get("import_stores"), list) else []

    rating_doc = read_doc(OZON_PRODUCT_RATING_PATH, default={"items": {}})
    rating_items = rating_doc.get("items") if isinstance(rating_doc, dict) else {}
    if not isinstance(rating_items, dict):
        rating_items = {}

    import_doc = read_doc(OZON_IMPORT_INFO_PATH, default={"items": {}})
    import_items = import_doc.get("items") if isinstance(import_doc, dict) else {}
    if not isinstance(import_items, dict):
        import_items = {}

    offer_ids = _offer_ids_for_product(product)
    ozon_stores: List[Dict[str, Any]] = []
    for store in stores:
        if not isinstance(store, dict):
            continue
        store_id = str(store.get("id") or "").strip()
        if not store_id:
            continue
        import_row = None
        rating_row = None
        for offer_id in offer_ids:
            maybe_import = import_items.get(f"{store_id}:{offer_id}")
            if isinstance(maybe_import, dict):
                import_row = maybe_import
            maybe_rating = rating_items.get(f"{store_id}:{offer_id}")
            if isinstance(maybe_rating, dict):
                rating_row = maybe_rating
            if import_row or rating_row:
                break
        status_code = str((import_row or {}).get("status") or (import_row or {}).get("state") or "").strip()
        status_label = str((import_row or {}).get("status") or "").strip()
        content_rating = (
            (rating_row or {}).get("rating")
            or (rating_row or {}).get("content_rating")
            or (rating_row or {}).get("score")
        )
        ozon_stores.append(
            {
                "store_id": store_id,
                "store_title": str(store.get("title") or store_id).strip(),
                "business_id": str(store.get("client_id") or "").strip(),
                "status_code": status_code,
                "status": status_label or _normalize_ozon_status(status_code),
                "content_rating": content_rating if str(content_rating or "").strip() else "Нет данных",
            }
        )

    ratings = [float(x.get("content_rating")) for x in ozon_stores if str(x.get("content_rating") or "").replace(".", "", 1).isdigit()]
    summary_rating = ""
    if ratings:
        summary_rating = str(int(ratings[0]) if ratings[0].is_integer() else ratings[0]) if min(ratings) == max(ratings) else f"{min(ratings):g}-{max(ratings):g}"
    has_mixed_status = len({str(x.get('status_code') or '') for x in ozon_stores if str(x.get('status_code') or '').strip()}) > 1
    has_mixed_ratings = len({str(x.get('content_rating') or '') for x in ozon_stores if str(x.get('content_rating') or '').strip() and str(x.get('content_rating') or '') != 'Нет данных'}) > 1
    return {
        "title": "OZON",
        "status": "Нет данных" if not ozon_stores else ("Есть расхождения" if has_mixed_status or has_mixed_ratings else ozon_stores[0].get("status") or "Нет данных"),
        "content_rating": summary_rating or "Нет данных",
        "stores_count": len(ozon_stores),
        "stores": ozon_stores,
    }


def _load_connectors_state() -> Dict[str, Any]:
    state = read_doc(CONNECTORS_STATE_PATH, default={"providers": {}})
    if not isinstance(state, dict):
        return {"providers": {}}
    providers = state.get("providers")
    if not isinstance(providers, dict):
        state["providers"] = {}
    return state


@router.get("/{product_id}/channels-summary")
def product_channels_summary(product_id: str):
    try:
        payload = get_product_service(product_id, include_variants=False)
    except JsonStoreError as e:
        raise _http_from_store_error(str(e))

    product = payload.get("product") if isinstance(payload, dict) else None
    if not isinstance(product, dict):
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")

    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    links = content.get("links") if isinstance(content.get("links"), list) else []
    links_by_label: Dict[str, str] = {}
    for item in links:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        if label and url and label not in links_by_label:
            links_by_label[label] = url

    state = _load_connectors_state()
    providers = state.get("providers") if isinstance(state, dict) else {}
    if not isinstance(providers, dict):
        providers = {}
    yandex_provider = providers.get("yandex_market") if isinstance(providers.get("yandex_market"), dict) else {}
    configured_yandex_stores = yandex_provider.get("import_stores") if isinstance(yandex_provider.get("import_stores"), list) else []

    cards_doc = read_doc(YANDEX_OFFER_CARDS_PATH, default={"items": {}})
    card_items = cards_doc.get("items") if isinstance(cards_doc, dict) else {}
    if not isinstance(card_items, dict):
        card_items = {}

    yandex_stores_by_id: Dict[str, Dict[str, Any]] = {}
    for store in configured_yandex_stores:
        if not isinstance(store, dict):
            continue
        store_id = str(store.get("id") or "").strip()
        if not store_id:
            continue
        yandex_stores_by_id[store_id] = {
            "store_id": store_id,
            "store_title": str(store.get("title") or store_id).strip(),
            "business_id": str(store.get("business_id") or "").strip(),
            "status_code": "",
            "status": "Нет данных",
            "content_rating": "Нет данных",
        }
    for offer_id in _offer_ids_for_product(product):
        row = card_items.get(offer_id)
        if not isinstance(row, dict):
            continue
        sources = row.get("sources") if isinstance(row.get("sources"), dict) else {}
        for source_key, src in sources.items():
            if not isinstance(src, dict):
                continue
            store_id = str(src.get("store_id") or source_key or "").strip()
            if not store_id or store_id.isdigit():
                continue
            card = src.get("card") if isinstance(src.get("card"), dict) else {}
            yandex_stores_by_id[store_id] = {
                "store_id": store_id,
                "store_title": str(src.get("store_title") or store_id).strip(),
                "business_id": str(src.get("business_id") or "").strip(),
                "status_code": str(card.get("cardStatus") or "").strip(),
                "status": _normalize_market_status(card.get("cardStatus") or ""),
                "content_rating": card.get("contentRating") if str(card.get("contentRating") or "").strip() else "Нет данных",
            }

    yandex_stores = list(yandex_stores_by_id.values())
    ratings = [int(x.get("content_rating")) for x in yandex_stores if str(x.get("content_rating") or "").strip().isdigit()]
    summary_rating = ""
    if ratings:
        summary_rating = str(ratings[0]) if min(ratings) == max(ratings) else f"{min(ratings)}-{max(ratings)}"

    yandex_summary = {
        "title": "Я.Маркет",
        "status": "Нет данных" if not yandex_stores else ("Есть расхождения" if len({str(x.get('status_code') or '') for x in yandex_stores}) > 1 or len(set(ratings)) > 1 else yandex_stores[0].get("status") or "Нет данных"),
        "content_rating": summary_rating or "Нет данных",
        "stores_count": len(yandex_stores),
        "stores": yandex_stores,
    }
    ozon_summary = _load_ozon_summary(product)

    return {
        "marketplaces": [
            yandex_summary,
            ozon_summary,
            {"title": "Wildberries", "status": "Нет данных", "content_rating": "Нет данных", "stores_count": 0, "stores": []},
        ],
        "external_systems": [
            {"title": "Сайт", "status": "Заглушка"},
            {"title": "1С", "status": "Заглушка"},
        ],
        "competitors": [
            {"key": "restore", "title": "Re:Store", "status": "Подключен" if str(links_by_label.get("restore") or "").strip() else "Не задан", "url": str(links_by_label.get("restore") or "").strip()},
            {"key": "store77", "title": "Store77", "status": "Подключен" if str(links_by_label.get("store77") or "").strip() else "Не задан", "url": str(links_by_label.get("store77") or "").strip()},
        ],
    }


@router.get("/new-bootstrap")
def products_new_bootstrap():
    payload = _product_new_bootstrap_payload()
    return {"ok": True, **payload}


@router.post("/create")
def products_create(req: CreateProductReq):
    try:
        p = create_product_service(req.model_dump())
        return {"product": p}
    except JsonStoreError as e:
        raise _http_from_store_error(str(e))


@router.get("/bulk")
def products_bulk(ids: str = Query(default="")):
    try:
        product_ids = [x.strip() for x in str(ids or "").split(",") if x.strip()]
        return get_products_bulk_service(product_ids)
    except JsonStoreError as e:
        raise _http_from_store_error(str(e))


@router.get("/{product_id}")
def products_get(product_id: str, include_variants: bool = True):
    try:
        return get_product_service(product_id, include_variants=include_variants)
    except JsonStoreError as e:
        raise _http_from_store_error(str(e))


@router.patch("/{product_id}")
def products_patch(product_id: str, req: PatchProductReq):
    try:
        patch = {k: v for k, v in req.model_dump().items() if v is not None}
        return patch_product_service(product_id, patch)  # ✅ сервис возвращает {"product": ...}
    except JsonStoreError as e:
        raise _http_from_store_error(str(e))


@router.get("/by-category/{category_id}")
def products_by_cat(category_id: str):
    return list_products_by_category_service(category_id)


@router.get("/find")
def products_find(sku_gt: Optional[str] = None):
    out = find_product_by_sku_service(sku_gt=sku_gt)
    if not out:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return out


class AllocateSkusReq(BaseModel):
    count: int = Field(default=1, ge=1, le=5000)


@router.post("/allocate-skus")
def products_allocate_skus(req: AllocateSkusReq):
    return allocate_sku_pairs_service(req.count)


def _sanitize_filename(name: str) -> str:
    raw = (name or "file").strip()
    if not raw:
        raw = "file"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in raw)
    if "." not in safe:
        safe = f"{safe}.bin"
    return safe


@router.post("/uploads")
async def products_uploads(
    files: List[UploadFile] = File(...),
    kind: str = Query(default="media"),
    product_id: Optional[str] = Query(default=None),
):
    kind_norm = (kind or "media").strip().lower()
    if kind_norm not in {"media", "media_images", "media_videos", "media_cover", "documents"}:
        raise HTTPException(status_code=400, detail="BAD_KIND")

    pid = (product_id or "").strip() or "common"
    storage_key = pid
    if pid and pid != "common":
        try:
            doc = load_products_repo()
            items = doc.get("items", []) if isinstance(doc, dict) else []
            hit = next((x for x in items if str((x or {}).get("id") or "").strip() == pid), None)
            if isinstance(hit, dict):
                sku_pim = str(hit.get("sku_pim") or "").strip()
                if sku_pim:
                    storage_key = sku_pim
        except Exception:
            storage_key = pid

    if not s3_enabled():
        raise HTTPException(status_code=503, detail="S3_NOT_CONFIGURED")

    out: List[Dict[str, Any]] = []
    for f in files or []:
        filename = _sanitize_filename(f.filename or "file.bin")
        stem, ext = (filename.rsplit(".", 1) + [""])[:2] if "." in filename else (filename, "bin")
        unique_name = f"{stem}_{uuid4().hex[:10]}.{ext}" if ext else f"{stem}_{uuid4().hex[:10]}"
        relative_key = f"{kind_norm}/{storage_key}/{unique_name}"

        content = await f.read()
        try:
            upload_bytes(relative_key, content, f.content_type or "application/octet-stream")
        except ObjectStorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        out.append(
            {
                "name": f.filename or unique_name,
                "url": f"/api/uploads/{relative_key}",
                "size": len(content),
                "content_type": f.content_type or "application/octet-stream",
            }
        )

    return {"items": out, "storage_key": storage_key}


@router.delete("/uploads")
def products_delete_upload(url: str = Query(...)):
    raw_url = str(url or "").strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="URL_REQUIRED")

    parsed = urlparse(raw_url)
    path_value = unquote(parsed.path or raw_url)
    prefix = "/api/uploads/"
    if not path_value.startswith(prefix):
        raise HTTPException(status_code=400, detail="BAD_UPLOAD_URL")

    relative = path_value[len(prefix):].lstrip("/")
    if not relative:
        raise HTTPException(status_code=400, detail="BAD_UPLOAD_URL")

    if not s3_enabled():
        raise HTTPException(status_code=503, detail="S3_NOT_CONFIGURED")
    try:
        delete_object(relative)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="UPLOAD_NOT_FOUND")
    except ObjectStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "deleted": raw_url}


class SeoDescriptionReq(BaseModel):
    source_a: str = Field(default="")
    source_b: str = Field(default="")
    use_features: bool = Field(default=False)
    features: List[Dict[str, Any]] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    tone: str = Field(default="Экспертный, понятный, без воды")
    max_chars: int = Field(default=2200, ge=300, le=8000)
    profile: str = Field(default="balanced")  # fast|balanced|quality
    model: Optional[str] = None


def _norm_keywords(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in items or []:
        s = str(x or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


SEO_FEATURE_STOP_WORDS = {
    "sku",
    "sku gt",
    "sku ids",
    "offerid",
    "offer id",
    "pim id",
    "ids id",
    "штрихкод",
    "партномер",
    "группа товара",
    "описание товара",
    "гарантийный срок",
    "срок службы",
    "страна производства",
    "ширина упаковки, мм",
    "длина упаковки, мм",
    "высота упаковки, мм",
    "вес упаковки, г",
    "ширина устройства, мм",
    "длина устройства, мм",
    "высота устройства, мм",
    "вес устройства, г",
    "толщина",
}

SEO_FEATURE_PRIORITY_WORDS = (
    "экран",
    "дисплей",
    "диагональ",
    "частота обновления",
    "процессор",
    "память",
    "оперативная",
    "встроенная",
    "камера",
    "аккумулятор",
    "батарея",
    "заряд",
    "связь",
    "5g",
    "nfc",
    "bluetooth",
    "wifi",
    "wi-fi",
    "sim",
    "esim",
    "операционная система",
    "os",
    "ios",
    "android",
    "звук",
    "динамик",
    "материал",
    "защита",
    "корпус",
    "цвет",
    "разрешение",
)


def _normalize_feature_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().replace("_", " ").split())


def _select_features_for_seo(items: List[Dict[str, str]], limit: int = 14) -> List[Dict[str, str]]:
    prepared: List[tuple[int, str, str, bool]] = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        required = bool(item.get("required"))
        if not name or not value:
            continue
        norm = _normalize_feature_name(name)
        if not norm or norm in seen:
            continue
        if norm in SEO_FEATURE_STOP_WORDS and not required:
            continue
        if len(value) > 120 and not required:
            continue
        score = 5 if required else 0
        if any(word in norm for word in SEO_FEATURE_PRIORITY_WORDS):
            score += 3
        if any(token in value.lower() for token in ("гб", "мп", "гц", "mah", "мАч", "nfc", "5g", "esim", "oled", "amoled", "retina")):
            score += 2
        if 3 <= len(value) <= 40:
            score += 1
        if norm in {"бренд", "цвет"}:
            score += 1
        prepared.append((score, name, value, required))
        seen.add(norm)
    prepared.sort(key=lambda item: (-item[0], item[1].lower()))
    return [{"name": name, "value": value, "required": required} for score, name, value, required in prepared[:limit]]


@router.post("/seo-description")
async def products_seo_description(req: SeoDescriptionReq):
    src_a = (req.source_a or "").strip()
    src_b = (req.source_b or "").strip()
    keywords = _norm_keywords(req.keywords or [])
    selected_features = _select_features_for_seo(req.features or [])
    feature_lines = []
    for item in selected_features:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or not value:
            continue
        feature_lines.append(f"- {name}: {value}")
    features_block = "\n".join(feature_lines)
    if not src_a and not src_b and not (req.use_features and features_block):
        raise HTTPException(status_code=400, detail="SOURCES_REQUIRED")

    api_base = os.getenv("LLM_API_BASE", "http://localhost:11434/v1").strip().rstrip("/")
    default_model = os.getenv("LLM_MODEL", "llama3.1:8b-instruct").strip()
    profile = (req.profile or "balanced").strip().lower()
    if profile not in {"fast", "balanced", "quality"}:
        profile = "balanced"
    profile_model_env = os.getenv(f"LLM_MODEL_{profile.upper()}", "").strip()
    model = (req.model or "").strip() or profile_model_env or default_model
    api_key = os.getenv("LLM_API_KEY", "").strip()

    use_features = bool(req.use_features and features_block)

    system_prompt = (
        "Ты SEO-редактор для e-commerce карточек. Пиши строго на русском языке.\\n"
        "Цель: создать готовое описание товара без участия человека.\\n"
        "Правила:\\n"
        "1) Только факты из источников; если факт не подтвержден — не добавляй.\\n"
        "2) Не используй канцелярит, воду и гиперболы.\\n"
        "3) Естественно интегрируй ключевые слова, без спама.\\n"
        "4) Не пиши заголовки с Markdown, только обычный текст.\\n"
        "5) Соблюдай длину и структуру ответа.\\n"
        "6) Если переданы характеристики товара, используй их как основной factual-слой описания.\\n"
        "7) Не копируй характеристики списком и не делай ответ табличным. Перестраивай их в естественный продающий текст.\\n"
        "8) Источники 1 и 2 используй как редакторский контекст: тон, формулировки, акценты, сценарии использования.\\n"
        "9) Ключевые слова встраивай органично, без повторов и SEO-спама.\\n"
        "10) Не тащи в описание служебные, логистические и технически второстепенные поля, если они не помогают продаже товара.\\n"
        "Структура ответа (обязательно):\\n"
        "- Абзац 1: 2-3 предложения с сутью товара и главной выгодой.\\n"
        "- Абзац 2: ключевые характеристики и преимущества.\\n"
        "- Абзац 3: сценарии использования/кому подходит.\\n"
        "- Абзац 4: короткий мягкий CTA (1 предложение)."
    )

    mode_hint = (
        "Режим генерации: опирайся в первую очередь на характеристики товара. "
        "Если в источниках есть маркетинговые формулировки, используй их только для стилистики и связок, "
        "но факты и преимущества собирай вокруг характеристик."
        if use_features
        else "Режим генерации: собери итоговое описание из двух источников и ключевых слов."
    )

    user_prompt = (
        f"Источник 1:\\n{src_a or '-'}\\n\\n"
        f"Источник 2:\\n{src_b or '-'}\\n\\n"
        f"Характеристики товара:\\n{features_block if use_features else '-'}\\n\\n"
        f"Ключевые слова: {', '.join(keywords) if keywords else '-'}\\n"
        f"Тон: {req.tone}\\n"
        f"{mode_hint}\\n"
        f"Ограничение длины: до {req.max_chars} символов\\n\\n"
        "Верни только готовый текст описания."
    )

    temperature = 0.35 if profile == "fast" else (0.5 if profile == "balanced" else 0.6)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
            res = await client.post(f"{api_base}/chat/completions", json=payload, headers=headers)
            if res.status_code == 404:
                native_base = api_base[:-3] if api_base.endswith("/v1") else api_base
                native_payload = {
                    "model": model,
                    "messages": payload["messages"],
                    "stream": False,
                    "options": {"temperature": temperature},
                }
                res = await client.post(f"{native_base}/api/chat", json=native_payload, headers=headers)
        if not res.is_success:
            raise HTTPException(status_code=502, detail=f"LLM_HTTP_{res.status_code}")

        body = res.json()
        description = (
            (((body.get("choices") or [{}])[0] or {}).get("message") or {}).get("content")
            or ((body.get("message") or {}).get("content"))
            or ""
        ).strip()
        if not description:
            raise HTTPException(status_code=502, detail="LLM_EMPTY_RESPONSE")

        if len(description) > req.max_chars:
            description = description[: req.max_chars].rstrip() + "…"

        return {"description": description, "model": model, "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        error_name = e.__class__.__name__
        error_message = str(e).strip()
        detail = f"LLM_ERROR:{error_name}"
        if error_message:
            detail = f"{detail}: {error_message}"
        raise HTTPException(status_code=502, detail=detail)
