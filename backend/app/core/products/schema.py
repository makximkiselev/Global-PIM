from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Optional


_ALLOWED_PRODUCT_TYPES = {"single", "multi"}
_ALLOWED_PRODUCT_STATUSES = {"draft", "active", "archived"}  # если у тебя другие — поменяй тут


def _strip_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# =========================
# Products
# =========================

class CreateProductReq(BaseModel):
    category_id: str = Field(min_length=1)
    type: str = Field(default="single")  # single|multi
    title: str = Field(min_length=1)

    sku_pim: Optional[str] = None
    sku_gt: Optional[str] = None

    selected_params: List[str] = Field(default_factory=list)
    feature_params: List[str] = Field(default_factory=list)

    exports_enabled: Dict[str, bool] = Field(default_factory=dict)

    @field_validator("category_id", "title", mode="before")
    @classmethod
    def _strip_required(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("field is required")
        return s

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type(cls, v: Any) -> str:
        s = str(v or "single").strip().lower()
        if s not in _ALLOWED_PRODUCT_TYPES:
            raise ValueError("BAD_TYPE")
        return s

    @field_validator("sku_pim", "sku_gt", mode="before")
    @classmethod
    def _strip_optional_skus(cls, v: Any) -> Optional[str]:
        return _strip_or_none(v)

    @field_validator("selected_params", "feature_params", mode="before")
    @classmethod
    def _normalize_param_lists(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("must be list")
        out: List[str] = []
        seen = set()
        for x in v:
            s = str(x or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out


class PatchProductReq(BaseModel):
    category_id: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    title: Optional[str] = None

    sku_gt: Optional[str] = None

    selected_params: Optional[List[str]] = None
    feature_params: Optional[List[str]] = None
    exports_enabled: Optional[Dict[str, bool]] = None

    @field_validator("category_id", "title", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Optional[str]:
        return _strip_or_none(v)

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type_optional(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip().lower()
        if s not in _ALLOWED_PRODUCT_TYPES:
            raise ValueError("BAD_TYPE")
        return s

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status_optional(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip().lower()
        if s not in _ALLOWED_PRODUCT_STATUSES:
            raise ValueError("BAD_STATUS")
        return s

    @field_validator("sku_gt", mode="before")
    @classmethod
    def _strip_optional_skus(cls, v: Any) -> Optional[str]:
        return _strip_or_none(v)

    @field_validator("selected_params", "feature_params", mode="before")
    @classmethod
    def _normalize_param_lists_optional(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("must be list")
        out: List[str] = []
        seen = set()
        for x in v:
            s = str(x or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out


# =========================
# Variants
# =========================

class GenerateVariantsReq(BaseModel):
    product_id: str = Field(min_length=1)
    selected_params: List[str] = Field(default_factory=list)
    values_by_param: Dict[str, List[Any]] = Field(default_factory=dict)

    @field_validator("product_id", mode="before")
    @classmethod
    def _strip_product_id(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("product_id is required")
        return s

    @field_validator("selected_params", mode="before")
    @classmethod
    def _normalize_selected_params(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("selected_params must be list")
        out: List[str] = []
        seen = set()
        for x in v:
            s = str(x or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    @field_validator("values_by_param", mode="before")
    @classmethod
    def _coerce_values_by_param(cls, v: Any) -> Dict[str, List[Any]]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("values_by_param must be dict")
        out: Dict[str, List[Any]] = {}
        for k, vals in v.items():
            kk = str(k or "").strip()
            if not kk:
                continue
            if vals is None:
                out[kk] = []
            elif isinstance(vals, list):
                out[kk] = vals
            else:
                # иногда фронт может прислать single value → приведём к списку
                out[kk] = [vals]
        return out


class BulkVariantRow(BaseModel):
    options: Dict[str, Any] = Field(default_factory=dict)
    variant_key: Optional[str] = None
    enabled: bool = True
    sku: Optional[str] = None
    sku_pim: Optional[str] = None
    sku_gt: Optional[str] = None
    title: Optional[str] = None
    links: Optional[List[Dict[str, Any]]] = None
    content: Optional[Dict[str, Any]] = None

    @field_validator("variant_key", "sku", "sku_pim", "sku_gt", "title", mode="before")
    @classmethod
    def _strip_optional_strings(cls, v: Any) -> Optional[str]:
        return _strip_or_none(v)


class BulkCreateVariantsReq(BaseModel):
    product_id: str = Field(min_length=1)
    selected_params: List[str] = Field(default_factory=list)
    rows: List[BulkVariantRow]

    @field_validator("product_id", mode="before")
    @classmethod
    def _strip_product_id(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("product_id is required")
        return s


class UpdateSkuReq(BaseModel):
    sku: str = Field(min_length=1)

    @field_validator("sku", mode="before")
    @classmethod
    def _strip_sku(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("sku is required")
        return s
