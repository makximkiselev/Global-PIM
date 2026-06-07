from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExportPayloadAudit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price_source: str = "unknown"
    media_count: int = Field(default=0, ge=0)
    attributes_total: int = Field(default=0, ge=0)
    attributes_with_source: int = Field(default=0, ge=0)
    attributes_without_source: int = Field(default=0, ge=0)
    missing_source: List[str] = Field(default_factory=list)

    @field_validator("price_source", mode="before")
    @classmethod
    def _price_source(cls, value: Any) -> str:
        return str(value or "").strip() or "unknown"

    @field_validator("missing_source", mode="before")
    @classmethod
    def _missing_source(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        out: List[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
            if len(out) >= 12:
                break
        return out


def export_payload_audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    audit = ExportPayloadAudit.model_validate(payload)
    if audit.attributes_without_source == 0 and audit.attributes_total >= audit.attributes_with_source:
        audit.attributes_without_source = max(0, audit.attributes_total - audit.attributes_with_source)
    return audit.model_dump()
