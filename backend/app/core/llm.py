from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx


class LlmError(RuntimeError):
    pass


def llm_model_for_profile(profile: str = "balanced", model: Optional[str] = None) -> tuple[str, str]:
    normalized_profile = str(profile or "balanced").strip().lower()
    if normalized_profile not in {"fast", "balanced", "quality"}:
        normalized_profile = "balanced"
    default_model = os.getenv("LLM_MODEL", "llama3.1:8b-instruct").strip()
    profile_model = os.getenv(f"LLM_MODEL_{normalized_profile.upper()}", "").strip()
    return (str(model or "").strip() or profile_model or default_model, normalized_profile)


async def llm_chat_text(
    *,
    messages: List[Dict[str, str]],
    profile: str = "balanced",
    model: Optional[str] = None,
    temperature: float = 0.2,
    timeout_seconds: float = 90.0,
    max_tokens: Optional[int] = None,
) -> Dict[str, str]:
    model_name, normalized_profile = llm_model_for_profile(profile, model)
    api_base = os.getenv("LLM_API_BASE", "http://localhost:11434/v1").strip().rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max(1, int(max_tokens))
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=15.0)) as client:
            res = await client.post(f"{api_base}/chat/completions", json=payload, headers=headers)
            if res.status_code == 404:
                native_base = api_base[:-3] if api_base.endswith("/v1") else api_base
                native_payload = {
                    "model": model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                }
                if max_tokens is not None:
                    native_payload["options"]["num_predict"] = max(1, int(max_tokens))
                res = await client.post(f"{native_base}/api/chat", json=native_payload, headers=headers)
    except Exception as exc:
        raise LlmError(f"LLM_ERROR:{exc.__class__.__name__}: {str(exc).strip()}") from exc

    if not res.is_success:
        raise LlmError(f"LLM_HTTP_{res.status_code}")

    body = res.json()
    content = (
        (((body.get("choices") or [{}])[0] or {}).get("message") or {}).get("content")
        or ((body.get("message") or {}).get("content"))
        or ""
    ).strip()
    if not content:
        raise LlmError("LLM_EMPTY_RESPONSE")

    return {"content": content, "model": model_name, "profile": normalized_profile}
