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


class AiCompetitorCandidateSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str = ""
    title: str = ""
    brand: str = ""
    sku: str = ""
    reason: str = ""

    @field_validator("url", "title", "brand", "sku", "reason", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return str(value or "").strip()


class AiCompetitorCandidatesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidates: List[AiCompetitorCandidateSuggestion] = Field(default_factory=list)


def parse_competitor_candidate_suggestions(text: str) -> List[Dict[str, Any]]:
    obj = json_object_from_text(text)
    raw_items = obj.get("candidates") if isinstance(obj.get("candidates"), list) else obj.get("items")
    if not isinstance(raw_items, list):
        return []
    parsed = AiCompetitorCandidatesResponse.model_validate({"candidates": raw_items})
    return [item.model_dump() for item in parsed.candidates if item.url]


class AiCompetitorSpecMappingSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_id: str = ""
    source_name: str = ""
    raw_value: str = ""
    action: str = ""
    target_code: str = ""
    target_name: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""

    @field_validator(
        "source_id",
        "source_name",
        "raw_value",
        "action",
        "target_code",
        "target_name",
        "reason",
        mode="before",
    )
    @classmethod
    def _text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence(cls, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value or 0.0)))
        except (TypeError, ValueError):
            return 0.0


class AiCompetitorSpecMappingsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: List[AiCompetitorSpecMappingSuggestion] = Field(default_factory=list)


def _coerce_competitor_spec_mapping(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "source_id": raw.get("source_id") or raw.get("sid") or "",
        "source_name": raw.get("source_name") or raw.get("n") or "",
        "raw_value": raw.get("raw_value") or raw.get("v") or "",
        "action": raw.get("action") or "",
        "target_code": raw.get("target_code") or raw.get("c") or "",
        "target_name": raw.get("target_name") or raw.get("tn") or "",
        "confidence": raw.get("confidence") or 0.0,
        "reason": raw.get("reason") or "",
    }


def parse_competitor_spec_mapping_suggestions(text: str) -> List[Dict[str, Any]]:
    obj = json_object_from_text(text)
    raw_items = obj.get("items")
    if not isinstance(raw_items, list):
        return []
    parsed = AiCompetitorSpecMappingsResponse.model_validate(
        {"items": [_coerce_competitor_spec_mapping(item) for item in raw_items]}
    )
    return [item.model_dump() for item in parsed.items if item.source_id and item.source_name]
