from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict, List, Optional

from app.api.routes import competitor_mapping
from app.core.tenant_context import (
    reset_current_tenant_organization_id,
    set_current_tenant_organization_id,
)
def _load_run(run_id: str) -> Dict[str, Any]:
    run = competitor_mapping._get_discovery_run(run_id)
    if not isinstance(run, dict):
        raise RuntimeError(f"Discovery run not found: {run_id}")
    return dict(run)


def _mark_failed(run_id: str, error: str) -> None:
    existing = competitor_mapping._get_discovery_run(run_id)
    sources: List[Dict[str, Any]] = []
    product_ids: Optional[List[str]] = None
    limit = 1
    use_ai = False
    if isinstance(existing, dict):
        sources = [
            competitor_mapping._source_by_id(str(source_id))
            for source_id in (existing.get("sources") or [])
            if str(source_id or "").strip()
        ]
        product_ids = existing.get("requested_product_ids") if isinstance(existing.get("requested_product_ids"), list) else None
        limit = int(existing.get("limit") or 1)
        use_ai = bool(existing.get("use_ai", False))
    competitor_mapping._persist_discovery_run(
        competitor_mapping._run_payload(
            run_id,
            status="failed",
            sources=sources,
            product_ids=product_ids,
            limit=limit,
            use_ai=use_ai,
            finished_at=competitor_mapping.now_iso(),
            errors=[{"error": error or "DISCOVERY_WORKER_FAILED"}],
        )
    )


async def run_once(run_id: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
    token = set_current_tenant_organization_id(organization_id) if organization_id else None
    try:
        run = _load_run(run_id)
        sources = [
            competitor_mapping._source_by_id(str(source_id))
            for source_id in (run.get("sources") or [])
            if str(source_id or "").strip()
        ]
        product_ids = run.get("requested_product_ids") if isinstance(run.get("requested_product_ids"), list) else None
        limit = int(run.get("limit") or 1)
        use_ai = bool(run.get("use_ai", False))
        return await competitor_mapping._execute_discovery_run_for_current_tenant(run_id, sources, product_ids, limit, use_ai=use_ai)
    except Exception as exc:
        _mark_failed(run_id, str(exc) or "DISCOVERY_WORKER_FAILED")
        raise
    finally:
        if token is not None:
            reset_current_tenant_organization_id(token)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one competitor discovery job.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--organization-id", default="")
    args = parser.parse_args()
    asyncio.run(run_once(args.run_id, args.organization_id or None))


if __name__ == "__main__":
    main()
