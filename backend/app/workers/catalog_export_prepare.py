from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict, Optional

from app.api.routes import catalog_exchange
from app.workers.workflow_runner import run_pending_workflow_jobs, run_workflow_loop, tenant_organization_scope


async def run_once(job_id: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
    with tenant_organization_scope(organization_id):
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


async def run_pending_once(organization_id: Optional[str] = None, *, limit: int = 5) -> Dict[str, Any]:
    return await run_pending_workflow_jobs(
        organization_id=organization_id,
        workflow=catalog_exchange._EXPORT_WORKFLOW,
        list_runs=catalog_exchange.list_pim_workflow_runs,
        run_one=lambda job_id: run_once(job_id),
        prune=catalog_exchange._prune_export_jobs,
        limit=limit,
        max_limit=50,
        default_error="EXPORT_JOB_FAILED",
    )


async def run_loop(
    organization_id: Optional[str] = None,
    *,
    poll_interval_seconds: float = 5.0,
    limit: int = 5,
) -> None:
    await run_workflow_loop(
        lambda: run_pending_once(organization_id, limit=limit),
        poll_interval_seconds=poll_interval_seconds,
    )


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
        asyncio.run(run_pending_once(organization_id, limit=args.limit))
        return
    if not str(args.job_id or "").strip():
        parser.error("--job-id is required unless --run-pending or --loop is used")
    asyncio.run(run_once(args.job_id, organization_id))


if __name__ == "__main__":
    main()
