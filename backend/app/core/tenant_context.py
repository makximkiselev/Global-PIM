from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from fastapi import Request

from app.core.auth import AuthContext
from app.core.control_plane import DEFAULT_ORGANIZATION_ID, get_organization_provisioning_status

_CURRENT_TENANT_ORGANIZATION_ID: ContextVar[str] = ContextVar(
    "current_tenant_organization_id",
    default=DEFAULT_ORGANIZATION_ID,
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class TenantContext:
    organization_id: str
    organization_slug: str
    organization_name: str
    organization_status: str
    tenant_status: str
    tenant_db_name: str
    tenant_db_host: str
    schema_version: Optional[str]
    ready: bool
    source: str = "session"


def resolve_tenant_context_from_auth(auth: Optional[AuthContext]) -> Optional[TenantContext]:
    if not auth or not auth.user:
        return None
    session = auth.session if isinstance(auth.session, dict) else {}
    organization_id = _normalize_text(session.get("current_organization_id"))
    if not organization_id:
        return None
    try:
        payload = get_organization_provisioning_status(organization_id)
    except Exception:
        return None
    organization = payload.get("organization") if isinstance(payload, dict) else {}
    tenant_registry = payload.get("tenant_registry") if isinstance(payload, dict) else {}
    if not isinstance(organization, dict):
        return None
    if not isinstance(tenant_registry, dict):
        tenant_registry = {}
    org_status = _normalize_text(organization.get("status")) or "unknown"
    tenant_status = _normalize_text(tenant_registry.get("status")) or org_status
    return TenantContext(
        organization_id=_normalize_text(organization.get("id")),
        organization_slug=_normalize_text(organization.get("slug")),
        organization_name=_normalize_text(organization.get("name")),
        organization_status=org_status,
        tenant_status=tenant_status,
        tenant_db_name=_normalize_text(tenant_registry.get("db_name")),
        tenant_db_host=_normalize_text(tenant_registry.get("db_host")),
        schema_version=_normalize_text(tenant_registry.get("schema_version")) or None,
        ready=tenant_status == "active" and org_status == "active",
    )


def tenant_context_payload(ctx: Optional[TenantContext]) -> Dict[str, Any]:
    if ctx is None:
        return {"resolved": False, "tenant": None}
    return {"resolved": True, "tenant": asdict(ctx)}


def current_tenant_organization_id() -> str:
    organization_id = _normalize_text(_CURRENT_TENANT_ORGANIZATION_ID.get())
    return organization_id or DEFAULT_ORGANIZATION_ID


def set_current_tenant_organization_id(organization_id: Optional[str]) -> Token[str]:
    normalized = _normalize_text(organization_id) or DEFAULT_ORGANIZATION_ID
    return _CURRENT_TENANT_ORGANIZATION_ID.set(normalized)


def reset_current_tenant_organization_id(token: Token[str]) -> None:
    _CURRENT_TENANT_ORGANIZATION_ID.reset(token)


def tenant_context_from_request(request: Request, require_ready: bool = False) -> TenantContext:
    ctx = getattr(request.state, "tenant", None)
    if not isinstance(ctx, TenantContext):
        raise ValueError("TENANT_CONTEXT_REQUIRED")
    if require_ready and not ctx.ready:
        raise ValueError("TENANT_NOT_READY")
    return ctx
