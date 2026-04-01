from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Path as ApiPath
from pydantic import BaseModel

from app.core.json_store import read_doc, write_doc

router = APIRouter(prefix="/ai/comfyui", tags=["ai-comfyui"])

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data" / "ai"
RUNS_PATH = DATA_DIR / "comfyui_runs.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_file_value(key: str) -> str:
    if not ENV_PATH.exists():
        return ""
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() != key:
                continue
            val = v.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            return val.strip()
    except Exception:
        return ""
    return ""


def _comfyui_base_url() -> str:
    return (
        os.getenv("COMFYUI_BASE_URL", "").strip()
        or _env_file_value("COMFYUI_BASE_URL")
        or "http://127.0.0.1:8188"
    ).rstrip("/")


def _comfyui_api_key() -> str:
    return os.getenv("COMFYUI_API_KEY", "").strip() or _env_file_value("COMFYUI_API_KEY")


def _http_headers() -> Dict[str, str]:
    token = _comfyui_api_key()
    if not token:
        return {"Accept": "application/json"}
    return {"Accept": "application/json", "Authorization": f"Bearer {token}"}


class ComfyPromptReq(BaseModel):
    prompt: Dict[str, Any]
    client_id: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


@router.get("/status")
async def comfyui_status() -> Dict[str, Any]:
    base = _comfyui_base_url()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(f"{base}/system_stats", headers=_http_headers())
        if not res.is_success:
            raise HTTPException(status_code=502, detail=f"COMFYUI_HTTP_FAILED {res.status_code}: {res.text[:300]}")
        body = res.json() if res.content else {}
        return {"ok": True, "base_url": base, "system_stats": body}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"COMFYUI_UNREACHABLE:{e}")


@router.post("/generate")
async def comfyui_generate(req: ComfyPromptReq) -> Dict[str, Any]:
    base = _comfyui_base_url()
    payload: Dict[str, Any] = {"prompt": req.prompt}
    if req.client_id:
        payload["client_id"] = req.client_id
    if isinstance(req.extra_data, dict):
        payload["extra_data"] = req.extra_data

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(f"{base}/prompt", json=payload, headers={**_http_headers(), "Content-Type": "application/json"})
        if not res.is_success:
            raise HTTPException(status_code=502, detail=f"COMFYUI_HTTP_FAILED {res.status_code}: {res.text[:500]}")
        body = res.json() if res.content else {}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"COMFYUI_PROMPT_ERROR:{e}")

    doc = read_doc(RUNS_PATH, default={"items": []})
    items = doc.get("items") if isinstance(doc, dict) else []
    if not isinstance(items, list):
        items = []
    items.insert(
        0,
        {
            "created_at": _now_iso(),
            "base_url": base,
            "prompt_id": body.get("prompt_id"),
            "number": body.get("number"),
            "node_errors": body.get("node_errors") or {},
        },
    )
    doc = {"items": items[:200]}
    write_doc(RUNS_PATH, doc)

    return {"ok": True, "queued": body}


@router.get("/history/{prompt_id}")
async def comfyui_history(prompt_id: str = ApiPath(..., min_length=1)) -> Dict[str, Any]:
    base = _comfyui_base_url()
    pid = str(prompt_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="PROMPT_ID_REQUIRED")

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            res = await client.get(f"{base}/history/{pid}", headers=_http_headers())
        if not res.is_success:
            raise HTTPException(status_code=502, detail=f"COMFYUI_HTTP_FAILED {res.status_code}: {res.text[:500]}")
        body = res.json() if res.content else {}
        return {"ok": True, "prompt_id": pid, "history": body}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"COMFYUI_HISTORY_ERROR:{e}")
