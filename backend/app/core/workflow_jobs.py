from __future__ import annotations

import time
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional

from app.storage.relational_pim_store import (
    claim_pim_workflow_run_as_running,
    get_pim_workflow_run,
    list_pim_workflow_runs,
    upsert_pim_workflow_run,
)

ATTR_AI_WORKFLOW = "marketplace_attribute_ai_match"
VALUE_AI_WORKFLOW = "marketplace_value_ai_match"
EXPORT_WORKFLOW = "catalog_export_prepare"

ATTR_AI_JOB_TTL_SECONDS = 300.0
VALUE_AI_JOB_TTL_SECONDS = 300.0
EXPORT_JOB_TTL_SECONDS = 900.0


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return backend_root().parent


def start_worker_process(module: str, job_id: str, organization_id: Optional[str]) -> None:
    normalized_module = str(module or "").strip()
    normalized_job_id = str(job_id or "").strip()
    if not normalized_module or not normalized_job_id:
        return
    env = os.environ.copy()
    backend_path = str(backend_root())
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = backend_path if not existing_pythonpath else f"{backend_path}{os.pathsep}{existing_pythonpath}"
    command = [sys.executable, "-m", normalized_module, "--job-id", normalized_job_id]
    normalized_org_id = str(organization_id or "").strip()
    if normalized_org_id:
        command.extend(["--organization-id", normalized_org_id])
    subprocess.Popen(
        command,
        cwd=str(repo_root()),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def start_attr_ai_match_worker_process(job_id: str, organization_id: Optional[str]) -> None:
    start_worker_process("app.workers.marketplace_attribute_ai_match", job_id, organization_id)


def start_value_ai_match_worker_process(job_id: str, organization_id: Optional[str]) -> None:
    start_worker_process("app.workers.marketplace_value_ai_match", job_id, organization_id)


def start_export_worker_process(job_id: str, organization_id: Optional[str]) -> None:
    start_worker_process("app.workers.catalog_export_prepare", job_id, organization_id)


def ai_match_timeout_seconds() -> float:
    try:
        return max(float(os.getenv("AI_MATCH_OLLAMA_TIMEOUT_SECONDS", "90.0") or "90.0"), 0.1)
    except (TypeError, ValueError):
        return 90.0


def ai_match_stale_after_seconds(base_ttl_seconds: float) -> float:
    return max(float(base_ttl_seconds), ai_match_timeout_seconds() * 2.5)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_ts(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def save_workflow_job(job: Dict[str, Any], *, workflow: str) -> Dict[str, Any]:
    upsert_pim_workflow_run(job, workflow=workflow)
    return job


def get_workflow_job(job_id: str, *, workflow: str) -> Optional[Dict[str, Any]]:
    return get_pim_workflow_run(str(job_id or "").strip(), workflow=workflow)


def list_workflow_jobs(
    *,
    workflow: str,
    status: Optional[str] = None,
    statuses: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    return list_pim_workflow_runs(workflow=workflow, status=status, statuses=statuses, limit=limit)


def claim_workflow_job(
    job_id: str,
    *,
    workflow: str,
    phase: str,
    message: str,
) -> Optional[Dict[str, Any]]:
    return claim_pim_workflow_run_as_running(
        str(job_id or "").strip(),
        workflow=workflow,
        payload_updates={
            "phase": phase,
            "message": message,
            "started_at": now_iso(),
            "updated_ts": time.time(),
        },
    )


def prune_stale_workflow_jobs(
    *,
    workflow: str,
    ttl_seconds: float,
    message: str,
    error: str,
    phase: str = "stale",
    limit: int = 200,
    now_ts: Optional[float] = None,
) -> int:
    now = float(now_ts if now_ts is not None else time.time())
    stale_count = 0
    for job in list_workflow_jobs(workflow=workflow, statuses=["queued", "running"], limit=limit):
        updated = job_ts(job.get("updated_ts") or job.get("created_ts"))
        if updated and now - updated > ttl_seconds:
            job.update(
                {
                    "status": "failed",
                    "phase": phase,
                    "message": message,
                    "finished_at": now_iso(),
                    "updated_ts": now,
                    "error": error,
                }
            )
            save_workflow_job(job, workflow=workflow)
            stale_count += 1
    return stale_count


def save_attr_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return save_workflow_job(job, workflow=ATTR_AI_WORKFLOW)


def claim_attr_ai_job(job_id: str) -> Optional[Dict[str, Any]]:
    return claim_workflow_job(
        job_id,
        workflow=ATTR_AI_WORKFLOW,
        phase="matching",
        message="AI подбирает спорные связки. Уверенные rule/memory-связки применяются автоматически.",
    )


def prune_attr_ai_jobs(*, stale_after_seconds: Optional[float] = None) -> int:
    return prune_stale_workflow_jobs(
        workflow=ATTR_AI_WORKFLOW,
        ttl_seconds=float(stale_after_seconds or ai_match_stale_after_seconds(ATTR_AI_JOB_TTL_SECONDS)),
        message="AI-подбор был прерван. Запустите подбор заново.",
        error="STALE_AI_MATCH_JOB",
    )


def save_value_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return save_workflow_job(job, workflow=VALUE_AI_WORKFLOW)


def claim_value_ai_job(job_id: str) -> Optional[Dict[str, Any]]:
    return claim_workflow_job(
        job_id,
        workflow=VALUE_AI_WORKFLOW,
        phase="matching",
        message="AI сопоставляет значения PIM со справочником площадки.",
    )


def prune_value_ai_jobs(*, stale_after_seconds: Optional[float] = None) -> int:
    return prune_stale_workflow_jobs(
        workflow=VALUE_AI_WORKFLOW,
        ttl_seconds=float(stale_after_seconds or ai_match_stale_after_seconds(VALUE_AI_JOB_TTL_SECONDS)),
        message="AI-сопоставление значений было прервано. Запустите подбор заново.",
        error="STALE_VALUE_AI_MATCH_JOB",
    )


def save_export_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return save_workflow_job(job, workflow=EXPORT_WORKFLOW)


def claim_export_job(job_id: str) -> Optional[Dict[str, Any]]:
    return claim_workflow_job(
        job_id,
        workflow=EXPORT_WORKFLOW,
        phase="preparing",
        message="Готовлю export batch: проверяю медиа, описание, категории, параметры и значения.",
    )


def prune_export_jobs() -> int:
    return prune_stale_workflow_jobs(
        workflow=EXPORT_WORKFLOW,
        ttl_seconds=EXPORT_JOB_TTL_SECONDS,
        message="Подготовка экспорта была прервана. Запустите проверку заново.",
        error="STALE_EXPORT_JOB",
    )
