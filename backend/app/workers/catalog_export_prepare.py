from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict, Optional

from app.api.routes import catalog_exchange
from app.core.tenant_context import (
    reset_current_tenant_organization_id,
    set_current_tenant_organization_id,
)
from app.workers.tenant_iteration import active_worker_organization_ids


async def run_once(job_id: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
    token = set_current_tenant_organization_id(organization_id) if organization_id else None
    try:
        catalog_exchange._prune_export_jobs()
        job = catalog_exchange._claim_export_job(job_id)
        if not isinstance(job, dict):
            return {
                "ok": False,
                "skipped": True,
                "job_id": job_id,
                "reason": "Export job is not queued or was already claimed.",
            }
        await asyncio.to_thread(catalog_exchange._run_catalog_export_job, job_id)
        return {"ok": True, "job_id": job_id}
    finally:
        if token is not None:
            reset_current_tenant_organization_id(token)


async def run_pending_once(organization_id: Optional[str] = None, *, limit: int = 5) -> Dict[str, Any]:
    token = set_current_tenant_organization_id(organization_id) if organization_id else None
    picked = 0
    completed = 0
    skipped = 0
    failed = 0
    errors: list[Dict[str, str]] = []
    try:
        catalog_exchange._prune_export_jobs()
        jobs = catalog_exchange.list_pim_workflow_runs(
            workflow=catalog_exchange._EXPORT_WORKFLOW,
            statuses=["queued"],
            limit=max(1, min(int(limit or 5), 50)),
        )
        for job in jobs:
            job_id = str(job.get("job_id") or job.get("id") or "").strip()
            if not job_id:
                continue
            picked += 1
            try:
                result = await run_once(job_id, organization_id)
                if isinstance(result, dict) and result.get("skipped"):
                    skipped += 1
                elif isinstance(result, dict) and result.get("ok") is False:
                    failed += 1
                    errors.append({"job_id": job_id, "error": str(result.get("reason") or "EXPORT_JOB_FAILED")[:500]})
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
    finally:
        if token is not None:
            reset_current_tenant_organization_id(token)


async def run_loop(
    organization_id: Optional[str] = None,
    *,
    poll_interval_seconds: float = 5.0,
    limit: int = 5,
) -> None:
    delay = max(float(poll_interval_seconds or 5.0), 0.5)
    while True:
        for org_id in active_worker_organization_ids(organization_id):
            await run_pending_once(org_id, limit=limit)
        await asyncio.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run catalog export preparation jobs.")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--run-pending", action="store_true", help="Run currently queued jobs once and exit.")
    parser.add_argument("--loop", action="store_true", help="Continuously poll queued jobs.")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--organization-id", default="")
    args = parser.parse_args()
    organization_id = args.organization_id or None
    if args.loop:
        asyncio.run(run_loop(organization_id, poll_interval_seconds=args.poll_interval, limit=args.limit))
        return
    if args.run_pending:
        async def _run_all_pending() -> None:
            for org_id in active_worker_organization_ids(organization_id):
                await run_pending_once(org_id, limit=args.limit)

        asyncio.run(_run_all_pending())
        return
    if not str(args.job_id or "").strip():
        parser.error("--job-id is required unless --run-pending or --loop is used")
    asyncio.run(run_once(args.job_id, organization_id))


if __name__ == "__main__":
    main()
