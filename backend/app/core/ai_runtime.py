from __future__ import annotations

import os

from fastapi import HTTPException


_ENABLED_VALUES = {"1", "true", "yes", "on"}


def ai_enabled() -> bool:
    return os.getenv("PIM_ENABLE_AI", "0").strip().lower() in _ENABLED_VALUES


def require_ai_enabled() -> None:
    if not ai_enabled():
        raise HTTPException(status_code=503, detail="AI_DISABLED")
