from __future__ import annotations

from typing import Any, Dict, List, Optional


PARAM_GROUPS: List[str] = ["Артикулы", "Описание", "Медиа", "О товаре", "Логистика", "Гарантия", "Прочее"]

BASE_TEMPLATE_FIELDS: List[Dict[str, Any]] = [
    {
        "key": "sku_gt",
        "name": "SKU GT",
        "code": "sku_gt",
        "type": "number",
        "required": True,
        "scope": "variant",
        "param_group": "Артикулы",
    },
    {
        "key": "sku_ids",
        "name": "SKU IDS",
        "code": "sku_id",
        "type": "number",
        "required": True,
        "scope": "variant",
        "param_group": "Артикулы",
    },
    {
        "key": "barcode",
        "name": "Штрихкод",
        "code": "barcode",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Артикулы",
    },
    {
        "key": "title",
        "name": "Наименование товара",
        "code": "title",
        "type": "text",
        "required": True,
        "scope": "common",
        "param_group": "О товаре",
    },
    {
        "key": "brand",
        "name": "Бренд",
        "code": "brand",
        "type": "select",
        "required": True,
        "scope": "common",
        "param_group": "О товаре",
    },
    {
        "key": "line",
        "name": "Линейка",
        "code": "line",
        "type": "select",
        "required": False,
        "scope": "common",
        "param_group": "О товаре",
    },
    {
        "key": "group",
        "name": "Группа товара",
        "code": "group_id",
        "type": "text",
        "required": False,
        "scope": "common",
        "param_group": "О товаре",
    },
    {
        "key": "description",
        "name": "Описание товара",
        "code": "description",
        "type": "text",
        "required": False,
        "scope": "common",
        "param_group": "Описание",
    },
    {
        "key": "media_images",
        "name": "Картинки",
        "code": "media_images",
        "type": "text",
        "required": False,
        "scope": "common",
        "param_group": "Медиа",
    },
    {
        "key": "media_videos",
        "name": "Видео",
        "code": "media_videos",
        "type": "text",
        "required": False,
        "scope": "common",
        "param_group": "Медиа",
    },
    {
        "key": "media_cover",
        "name": "Видеообложка",
        "code": "media_cover",
        "type": "text",
        "required": False,
        "scope": "common",
        "param_group": "Медиа",
    },
    {
        "key": "package_width",
        "name": "Ширина упаковки, мм",
        "code": "package_width",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "package_length",
        "name": "Длина упаковки, мм",
        "code": "package_length",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "package_height",
        "name": "Высота упаковки, мм",
        "code": "package_height",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "device_width",
        "name": "Ширина устройства, мм",
        "code": "device_width",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "device_length",
        "name": "Длина устройства, мм",
        "code": "device_length",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "device_height",
        "name": "Высота устройства, мм",
        "code": "device_height",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "package_weight",
        "name": "Вес упаковки, г",
        "code": "package_weight",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "device_weight",
        "name": "Вес устройства, г",
        "code": "device_weight",
        "type": "number",
        "required": False,
        "scope": "common",
        "param_group": "Логистика",
    },
    {
        "key": "service_life",
        "name": "Срок службы",
        "code": "service_life",
        "type": "text",
        "required": False,
        "scope": "common",
        "param_group": "Гарантия",
    },
    {
        "key": "country_of_origin",
        "name": "Страна производства",
        "code": "country_of_origin",
        "type": "select",
        "required": False,
        "scope": "common",
        "param_group": "Гарантия",
    },
    {
        "key": "warranty_period",
        "name": "Гарантийный срок",
        "code": "warranty_period",
        "type": "text",
        "required": False,
        "scope": "common",
        "param_group": "Гарантия",
    },
]


def _norm_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


BASE_FIELD_BY_KEY: Dict[str, Dict[str, Any]] = {str(item["key"]): item for item in BASE_TEMPLATE_FIELDS}
BASE_FIELD_BY_CODE: Dict[str, Dict[str, Any]] = {str(item["code"]).lower(): item for item in BASE_TEMPLATE_FIELDS}
BASE_FIELD_BY_NAME: Dict[str, Dict[str, Any]] = {_norm_name(item["name"]): item for item in BASE_TEMPLATE_FIELDS}
BASE_FIELD_CODE_ALIASES: Dict[str, str] = {
    "sku_ids": "sku_id",
    "group": "group_id",
    "media": "media_images",
}
BASE_FIELD_NAME_ALIASES: Dict[str, str] = {
    _norm_name("Ширина упаковки"): _norm_name("Ширина упаковки, мм"),
    _norm_name("Длина упаковки"): _norm_name("Длина упаковки, мм"),
    _norm_name("Высота упаковки"): _norm_name("Высота упаковки, мм"),
    _norm_name("Ширина устройства"): _norm_name("Ширина устройства, мм"),
    _norm_name("Длина устройства"): _norm_name("Длина устройства, мм"),
    _norm_name("Высота устройства"): _norm_name("Высота устройства, мм"),
    _norm_name("Вес упаковки"): _norm_name("Вес упаковки, г"),
    _norm_name("Вес устройства"): _norm_name("Вес устройства, г"),
}
DEPRECATED_TEMPLATE_CODES = {"product_type", "country", "sku_pim"}
DEPRECATED_TEMPLATE_NAMES = {"тип товара", "sku pim"}


def base_template_fields() -> List[Dict[str, Any]]:
    return [dict(item) for item in BASE_TEMPLATE_FIELDS]


def base_field_by_key(key: Any) -> Optional[Dict[str, Any]]:
    return dict(BASE_FIELD_BY_KEY[str(key)]) if str(key) in BASE_FIELD_BY_KEY else None


def base_field_by_code(code: Any) -> Optional[Dict[str, Any]]:
    key = str(code or "").strip().lower()
    key = BASE_FIELD_CODE_ALIASES.get(key, key)
    return dict(BASE_FIELD_BY_CODE[key]) if key in BASE_FIELD_BY_CODE else None


def base_field_by_name(name: Any) -> Optional[Dict[str, Any]]:
    key = BASE_FIELD_NAME_ALIASES.get(_norm_name(name), _norm_name(name))
    return dict(BASE_FIELD_BY_NAME[key]) if key in BASE_FIELD_BY_NAME else None


def canonical_base_field_name(name: Any = None, code: Any = None) -> str:
    field = None
    if code is not None:
        field = base_field_by_code(code)
    if not field and name is not None:
        field = base_field_by_name(name)
    if field:
        return str(field.get("name") or "").strip()
    return str(name or "").strip()


def is_base_field_name(name: Any) -> bool:
    return base_field_by_name(name) is not None


def is_base_field_code(code: Any) -> bool:
    return base_field_by_code(code) is not None


def template_attr_layer(attr: Dict[str, Any]) -> str:
    if not isinstance(attr, dict):
        return "category"
    options = attr.get("options") if isinstance(attr.get("options"), dict) else {}
    layer = str(options.get("layer") or "").strip().lower()
    if layer in {"base", "category"}:
        return layer
    if is_base_field_code(attr.get("code")) or is_base_field_name(attr.get("name")):
        return "base"
    return "category"


def split_template_attrs(attrs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    base_attrs: List[Dict[str, Any]] = []
    category_attrs: List[Dict[str, Any]] = []
    for attr in attrs or []:
        if template_attr_layer(attr) == "base":
            base_attrs.append(attr)
        else:
            category_attrs.append(attr)
    return {"base": base_attrs, "category": category_attrs}


def is_deprecated_template_code(code: Any) -> bool:
    return str(code or "").strip().lower() in DEPRECATED_TEMPLATE_CODES


def is_deprecated_template_name(name: Any) -> bool:
    return _norm_name(name) in DEPRECATED_TEMPLATE_NAMES
