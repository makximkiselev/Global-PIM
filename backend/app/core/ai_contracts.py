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
