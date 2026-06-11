from __future__ import annotations

from typing import List, Optional

from app.core.control_plane import DEFAULT_ORGANIZATION_ID, list_organizations_overview


def active_worker_organization_ids(organization_id: Optional[str] = None) -> List[str]:
    explicit = str(organization_id or "").strip()
    if explicit:
        return [explicit]
    try:
        organizations = list_organizations_overview()
    except Exception:
        return [DEFAULT_ORGANIZATION_ID]
    out: List[str] = []
    for organization in organizations:
        org_id = str((organization or {}).get("id") or "").strip()
        status = str((organization or {}).get("status") or "").strip().lower()
        tenant_status = str((organization or {}).get("tenant_status") or "").strip().lower()
        if not org_id or status != "active":
            continue
        if tenant_status and tenant_status != "active":
            continue
        out.append(org_id)
    return out or [DEFAULT_ORGANIZATION_ID]
