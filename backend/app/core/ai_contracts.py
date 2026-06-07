from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


def json_object_from_text(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.I).strip()
        raw = re.sub(r"```$", "", raw).strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


class AiValuePairSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    canonical: str = ""
    output: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""

    @field_validator("canonical", "output", "reason", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return str(value or "").strip()


class AiValuePairsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pairs: List[AiValuePairSuggestion] = Field(default_factory=list)


def parse_value_pair_suggestions(text: str) -> List[Dict[str, Any]]:
    parsed = AiValuePairsResponse.model_validate(json_object_from_text(text))
    return [item.model_dump() for item in parsed.pairs if item.canonical and item.output]


class AiAttributeRowSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    catalog_name: str = ""
    group: str = ""
    yandex_id: str = ""
    confirmed: bool = False

    @field_validator("catalog_name", "group", "yandex_id", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return str(value or "").strip()


class AiAttributeRowsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rows: List[AiAttributeRowSuggestion] = Field(default_factory=list)


def _coerce_attribute_row(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return {
            "catalog_name": raw.get("catalog_name") or raw.get("pim_name") or raw.get("name") or "",
            "group": raw.get("group") or "",
            "yandex_id": raw.get("yandex_id") or raw.get("market_id") or raw.get("provider_id") or "",
            "confirmed": bool(raw.get("confirmed") or False),
        }
    if isinstance(raw, list):
        return {
            "catalog_name": raw[0] if len(raw) > 0 else "",
            "group": "",
            "yandex_id": raw[1] if len(raw) > 1 else "",
            "confirmed": True,
        }
    return {}


def parse_attribute_row_suggestions(text: str) -> List[Dict[str, Any]]:
    obj = json_object_from_text(text)
    rows = obj.get("rows") if isinstance(obj.get("rows"), list) else None
    if rows is None and obj.get("pim_name"):
        rows = [obj]
    if not isinstance(rows, list):
        return []
    parsed = AiAttributeRowsResponse.model_validate({"rows": [_coerce_attribute_row(row) for row in rows]})
    return [item.model_dump() for item in parsed.rows if item.catalog_name]
