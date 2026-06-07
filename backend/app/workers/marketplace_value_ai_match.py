from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict, Optional

from app.api.routes import marketplace_mapping
from app.workers.workflow_runner import run_pending_workflow_jobs, run_workflow_loop, tenant_organization_scope


async def run_once(job_id: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
    with tenant_organization_scope(organization_id):
        marketplace_mapping._prune_value_ai_jobs()
        job = marketplace_mapping._claim_value_ai_job(job_id)
        if not isinstance(job, dict):
            return {
                "ok": False,
                "skipped": True,
                "job_id": job_id,
                "reason": "Value AI matching job is not queued or was already claimed.",
            }
        catalog_category_id = str(job.get("catalog_category_id") or "").strip()
        dict_id = str(job.get("dict_id") or "").strip()
        provider = str(job.get("provider") or "").strip()
        if not catalog_category_id or not dict_id or not provider:
            raise RuntimeError(f"Value AI matching job has incomplete payload: {job_id}")
        req = marketplace_mapping.ValueAiSuggestReq(provider=provider, apply=bool(job.get("apply", True)))
        await marketplace_mapping._run_value_ai_match_job(job_id, catalog_category_id, dict_id, req)
        return {
            "ok": True,
            "job_id": job_id,
            "catalog_category_id": catalog_category_id,
            "dict_id": dict_id,
            "provider": provider,
        }


async def run_pending_once(organization_id: Optional[str] = None, *, limit: int = 10) -> Dict[str, Any]:
    return await run_pending_workflow_jobs(
        organization_id=organization_id,
        workflow=marketplace_mapping._VALUE_AI_WORKFLOW,
        list_runs=marketplace_mapping.list_pim_workflow_runs,
        run_one=lambda job_id: run_once(job_id),
        prune=marketplace_mapping._prune_value_ai_jobs,
        limit=limit,
        max_limit=100,
        default_error="VALUE_AI_MATCH_JOB_FAILED",
    )


async def run_loop(
    organization_id: Optional[str] = None,
    *,
    poll_interval_seconds: float = 5.0,
    limit: int = 10,
) -> None:
    await run_workflow_loop(
        lambda: run_pending_once(organization_id, limit=limit),
        poll_interval_seconds=poll_interval_seconds,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one marketplace value AI matching job.")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--run-pending", action="store_true", help="Run currently queued jobs once and exit.")
    parser.add_argument("--loop", action="store_true", help="Continuously poll queued jobs.")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=10)
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
