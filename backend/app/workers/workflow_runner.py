from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Awaitable, Callable, Dict, Iterator, List, Optional

from app.core.tenant_context import (
    reset_current_tenant_organization_id,
    set_current_tenant_organization_id,
)

RunListFn = Callable[..., List[Dict[str, Any]]]
RunOneFn = Callable[[str], Awaitable[Dict[str, Any]]]
PruneFn = Callable[[], None]


@contextmanager
def tenant_organization_scope(organization_id: Optional[str]) -> Iterator[None]:
    token = set_current_tenant_organization_id(organization_id) if organization_id else None
    try:
        yield
    finally:
        if token is not None:
            reset_current_tenant_organization_id(token)


def workflow_job_id(row: Dict[str, Any]) -> str:
    return str(row.get("job_id") or row.get("id") or row.get("run_id") or "").strip()


async def run_pending_workflow_jobs(
    *,
    organization_id: Optional[str],
    workflow: str,
    list_runs: RunListFn,
    run_one: RunOneFn,
    prune: Optional[PruneFn] = None,
    limit: int = 10,
    max_limit: int = 100,
    default_error: str = "WORKFLOW_JOB_FAILED",
) -> Dict[str, Any]:
    picked = 0
    completed = 0
    skipped = 0
    failed = 0
    errors: list[Dict[str, str]] = []
    safe_limit = max(1, min(int(limit or 10), max(1, int(max_limit or 100))))

    with tenant_organization_scope(organization_id):
        if prune is not None:
            prune()
        jobs = list_runs(workflow=workflow, statuses=["queued"], limit=safe_limit)
        for job in jobs:
            job_id = workflow_job_id(job)
            if not job_id:
                continue
            picked += 1
            try:
                result = await run_one(job_id)
                if isinstance(result, dict) and result.get("skipped"):
                    skipped += 1
                elif isinstance(result, dict) and result.get("ok") is False:
                    failed += 1
                    errors.append({"job_id": job_id, "error": str(result.get("reason") or default_error)[:500]})
                else:
                    completed += 1
            except Exception as exc:
                failed += 1
                errors.append({"job_id": job_id, "error": str(exc)[:500]})

    return {
        "ok": failed == 0,
        "picked": picked,
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
    }


async def run_workflow_loop(
    run_pending: Callable[[], Awaitable[Dict[str, Any]]],
    *,
    poll_interval_seconds: float = 5.0,
) -> None:
    delay = max(float(poll_interval_seconds or 5.0), 0.5)
    while True:
        await run_pending()
        await asyncio.sleep(delay)
