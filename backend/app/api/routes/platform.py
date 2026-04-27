from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.routes.auth import require_auth
from app.core.auth import (
    SESSION_COOKIE,
    auth_cookie_secure,
    build_auth_context,
    create_session,
    ensure_user_account,
    find_user_by_login_or_email,
    load_auth_base_db,
    session_payload,
    update_session_current_organization,
)
from app.core.control_plane import (
    accept_organization_invite,
    can_access_organization,
    create_organization_invite,
    create_organization_with_owner,
    get_organization_provisioning_status,
    list_organization_invites,
    list_organization_members,
    list_organizations_overview,
)
from app.core.tenant_context import tenant_context_payload

router = APIRouter(prefix="/platform", tags=["platform"])


class OrganizationSwitchReq(BaseModel):
    organization_id: str


class RegisterReq(BaseModel):
    email: str
    password: str
    name: str
    organization_name: str


class InviteCreateReq(BaseModel):
    email: str
    org_role_code: str


class InviteAcceptReq(BaseModel):
    token: str
    email: str
    name: str | None = None
    password: str | None = None


def _resolve_requested_organization(auth, organization_id: str | None = None) -> str:
    payload = session_payload(auth.user, auth.roles, session=auth.session)
    available = payload.get("organizations") or []
    target_id = str(organization_id or payload.get("current_organization", {}).get("id") or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="CURRENT_ORGANIZATION_REQUIRED")
    if not can_access_organization(auth.user, auth.roles, target_id):
        raise HTTPException(status_code=403, detail="ORGANIZATION_FORBIDDEN")
    if not any(str(row.get("id") or "").strip() == target_id for row in available):
        raise HTTPException(status_code=403, detail="ORGANIZATION_FORBIDDEN")
    return target_id


@router.get("/organizations")
def list_organizations(auth=Depends(require_auth)):
    payload = session_payload(auth.user, auth.roles, session=auth.session)
    return {
        "ok": True,
        "organizations": payload.get("organizations") or [],
        "current_organization": payload.get("current_organization"),
        "platform_roles": payload.get("platform_roles") or [],
        "flags": payload.get("flags") or {},
    }


@router.get("/workspace/bootstrap")
def workspace_bootstrap(request: Request, organization_id: str | None = None, auth=Depends(require_auth)):
    payload = session_payload(auth.user, auth.roles, session=auth.session)
    target_id = _resolve_requested_organization(auth, organization_id)
    accessible_ids = [str(row.get("id") or "").strip() for row in (payload.get("organizations") or []) if str(row.get("id") or "").strip()]
    organizations = list_organizations_overview(accessible_ids)
    selected_organization = next((row for row in organizations if row["id"] == target_id), None)
    if selected_organization is None:
        raise HTTPException(status_code=404, detail="ORGANIZATION_NOT_FOUND")
    return {
        "ok": True,
        "organizations": organizations,
        "selected_organization": selected_organization,
        "members": list_organization_members(target_id),
        "invites": list_organization_invites(target_id),
        "tenant": tenant_context_payload(getattr(request.state, "tenant", None)),
        "platform_roles": payload.get("platform_roles") or [],
        "flags": payload.get("flags") or {},
    }


@router.get("/organizations/current/status")
def current_organization_status(auth=Depends(require_auth)):
    payload = session_payload(auth.user, auth.roles, session=auth.session)
    current_organization = payload.get("current_organization") or {}
    organization_id = str(current_organization.get("id") or "").strip()
    if not organization_id:
        raise HTTPException(status_code=400, detail="CURRENT_ORGANIZATION_REQUIRED")
    try:
        status_payload = get_organization_provisioning_status(organization_id)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if detail == "ORGANIZATION_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail=detail)
    return {"ok": True, **status_payload}


@router.get("/tenant/current")
def current_tenant_context(request: Request, _auth=Depends(require_auth)):
    return {"ok": True, **tenant_context_payload(getattr(request.state, "tenant", None))}


@router.post("/organizations/switch")
def switch_organization(payload: OrganizationSwitchReq, auth=Depends(require_auth)):
    if not auth.session_id:
        raise HTTPException(status_code=400, detail="SESSION_NOT_FOUND")
    organization_id = str(payload.organization_id or "").strip()
    if not organization_id:
        raise HTTPException(status_code=400, detail="ORGANIZATION_REQUIRED")
    try:
        updated_session = update_session_current_organization(auth, organization_id)
    except ValueError as exc:
        detail = str(exc)
        status = 403 if detail == "ORGANIZATION_FORBIDDEN" else 400
        raise HTTPException(status_code=status, detail=detail)
    return session_payload(auth.user, auth.roles, session=updated_session)


@router.post("/register")
def register(payload: RegisterReq, response: Response):
    email = str(payload.email or "").strip().lower()
    password = str(payload.password or "")
    name = str(payload.name or "").strip()
    organization_name = str(payload.organization_name or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="EMAIL_REQUIRED")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="PASSWORD_TOO_SHORT")
    if not organization_name:
        raise HTTPException(status_code=400, detail="ORGANIZATION_NAME_REQUIRED")
    if find_user_by_login_or_email(email):
        raise HTTPException(status_code=409, detail="EMAIL_ALREADY_EXISTS")
    try:
        user = ensure_user_account(login=email, password=password, name=name or email, email=email, role_code="owner")
        organization = create_organization_with_owner(user, organization_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = create_session(str(user.get("id") or ""), current_organization_id=str(organization.get("id") or ""))
    db = load_auth_base_db()
    roles = build_auth_context(db, db.get("users", {}).get(str(user.get("id") or ""))).roles
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=auth_cookie_secure(),
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return session_payload(user, roles, session={"current_organization_id": organization["id"]})


@router.post("/organizations/{organization_id}/invites")
def create_invite(organization_id: str, payload: InviteCreateReq, auth=Depends(require_auth)):
    target_id = _resolve_requested_organization(auth, organization_id)
    try:
        invite = create_organization_invite(
            organization_id=target_id,
            email=payload.email,
            org_role_code=payload.org_role_code,
            created_by_user_id=str((auth.user or {}).get("id") or ""),
        )
    except ValueError as exc:
        detail = str(exc)
        status = 404 if detail == "ORGANIZATION_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail=detail)
    return {"ok": True, "invite": invite}


@router.post("/invites/accept")
def accept_invite(payload: InviteAcceptReq, response: Response):
    email = str(payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="EMAIL_REQUIRED")
    user = find_user_by_login_or_email(email)
    if user is None:
        password = str(payload.password or "")
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="PASSWORD_TOO_SHORT")
        user = ensure_user_account(
            login=email,
            password=password,
            name=str(payload.name or "").strip() or email,
            email=email,
            role_code="viewer",
        )
    try:
        accepted = accept_organization_invite(payload.token, str(user.get("id") or ""))
    except ValueError as exc:
        detail = str(exc)
        status = 404 if detail == "INVITE_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail=detail)
    token = create_session(str(user.get("id") or ""), current_organization_id=str(accepted["organization"]["id"] or ""))
    db = load_auth_base_db()
    roles = build_auth_context(db, db.get("users", {}).get(str(user.get("id") or ""))).roles
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=auth_cookie_secure(),
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return session_payload(user, roles, session={"current_organization_id": accepted["organization"]["id"]})
