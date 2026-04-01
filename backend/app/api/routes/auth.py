from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.auth import (
    ACTION_CATALOG,
    PAGE_CATALOG,
    SESSION_COOKIE,
    admin_reset_password,
    auth_cookie_secure,
    auth_from_request,
    authenticate,
    build_auth_context,
    change_password,
    create_session,
    drop_session,
    ensure_owner_account,
    find_role_by_code,
    has_action,
    load_auth_db,
    recent_login_events,
    record_login_failure,
    record_login_success,
    save_auth_db,
    session_payload,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginReq(BaseModel):
    login: str
    password: str


class RoleReq(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    pages: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)


class UserReq(BaseModel):
    login: str
    name: str
    email: Optional[str] = None
    role_ids: List[str] = Field(default_factory=list)
    is_active: bool = True
    password: Optional[str] = None


class ChangePasswordReq(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordReq(BaseModel):
    password: Optional[str] = None


def _client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "").strip()


def _user_agent(request: Request) -> str:
    return str(request.headers.get("user-agent") or "").strip()


def current_auth(request: Request):
    auth = auth_from_request(request)
    request.state.auth = auth
    return auth


def require_auth(request: Request):
    auth = current_auth(request)
    if not auth.user:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    return auth


def require_action(action_code: str):
    def _dep(request: Request):
        auth = require_auth(request)
        if not has_action(auth, action_code):
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        return auth

    return _dep


def _auth_is_owner(auth) -> bool:
    return any(str((role or {}).get("code") or "").strip().lower() == "owner" for role in (auth.roles or []))


def _user_has_role_code(user: Dict[str, Any], roles_map: Dict[str, Dict[str, Any]], code: str) -> bool:
    target = str(code or "").strip().lower()
    if not target:
        return False
    for rid in user.get("role_ids") or []:
        role = roles_map.get(str(rid))
        if isinstance(role, dict) and str(role.get("code") or "").strip().lower() == target:
            return True
    return False


def _visible_roles(auth, roles_map: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if _auth_is_owner(auth):
        return {rid: role for rid, role in roles_map.items() if isinstance(role, dict)}
    out: Dict[str, Dict[str, Any]] = {}
    for rid, role in roles_map.items():
        if not isinstance(role, dict):
            continue
        if bool(role.get("is_system")):
            continue
        if str(role.get("code") or "").strip().lower() == "owner":
            continue
        out[rid] = role
    return out


def _visible_users(auth, users_map: Dict[str, Dict[str, Any]], roles_map: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if _auth_is_owner(auth):
        return {uid: user for uid, user in users_map.items() if isinstance(user, dict)}
    out: Dict[str, Dict[str, Any]] = {}
    for uid, user in users_map.items():
        if not isinstance(user, dict):
            continue
        if _user_has_role_code(user, roles_map, "owner"):
            continue
        out[uid] = user
    return out


def _assert_role_manageable(auth, role: Dict[str, Any]) -> None:
    if _auth_is_owner(auth):
        return
    if bool(role.get("is_system")) or str(role.get("code") or "").strip().lower() == "owner":
        raise HTTPException(status_code=403, detail="FORBIDDEN")


def _assert_user_manageable(auth, user: Dict[str, Any], roles_map: Dict[str, Dict[str, Any]]) -> None:
    if _auth_is_owner(auth):
        return
    if _user_has_role_code(user, roles_map, "owner"):
        raise HTTPException(status_code=403, detail="FORBIDDEN")


def _role_public(role: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": role.get("id"),
        "code": role.get("code"),
        "name": role.get("name"),
        "description": role.get("description"),
        "pages": role.get("pages") or [],
        "actions": role.get("actions") or [],
        "is_system": bool(role.get("is_system")),
    }


def _user_public(user: Dict[str, Any], roles_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    role_ids = [str(x) for x in (user.get("role_ids") or []) if str(x).strip()]
    return {
        "id": user.get("id"),
        "login": user.get("login"),
        "email": user.get("email"),
        "name": user.get("name"),
        "role_ids": role_ids,
        "roles": [_role_public(roles_map[rid]) for rid in role_ids if isinstance(roles_map.get(rid), dict)],
        "is_active": bool(user.get("is_active", True)),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "last_login_at": user.get("last_login_at"),
        "last_login_ip": user.get("last_login_ip"),
    }


@router.get("/session")
def auth_session(request: Request):
    auth = current_auth(request)
    if not auth.user:
        return {"authenticated": False, "catalog": {"pages": PAGE_CATALOG, "actions": ACTION_CATALOG}}
    return session_payload(auth.user, auth.roles)


@router.post("/login")
def auth_login(payload: LoginReq, request: Request, response: Response):
    user = authenticate(payload.login, payload.password)
    if not user:
        record_login_failure(payload.login, ip=_client_ip(request), user_agent=_user_agent(request))
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")
    user = record_login_success(str(user.get("id") or ""), ip=_client_ip(request), user_agent=_user_agent(request)) or user
    token = create_session(str(user.get("id") or ""))
    db = load_auth_db()
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
    return session_payload(user, roles)


@router.post("/change-password")
def auth_change_password(payload: ChangePasswordReq, auth=Depends(require_auth)):
    current = str(payload.current_password or "")
    new = str(payload.new_password or "")
    if len(new) < 8:
        raise HTTPException(status_code=400, detail="PASSWORD_TOO_SHORT")
    try:
        change_password(str(auth.user.get("id") or ""), current, new)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/logout")
def auth_logout(request: Request, response: Response):
    token = str(request.cookies.get(SESSION_COOKIE) or "").strip()
    if token:
        drop_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/admin/bootstrap-owner")
def bootstrap_owner_info(_auth=Depends(require_action("users.manage"))):
    db = load_auth_db()
    role = find_role_by_code(db, "owner")
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    roles_map = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    owner_users = [
        _user_public(user, roles_map)
        for user in users.values()
        if isinstance(user, dict) and role and role["id"] in [str(x) for x in (user.get("role_ids") or [])]
    ]
    return {"ok": True, "owner_users": owner_users}


@router.get("/admin/roles")
def admin_roles(_auth=Depends(require_action("roles.manage"))):
    db = load_auth_db()
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    visible_roles = _visible_roles(_auth, roles)
    return {
        "ok": True,
        "roles": [_role_public(role) for role in visible_roles.values() if isinstance(role, dict)],
        "catalog": {"pages": PAGE_CATALOG, "actions": ACTION_CATALOG},
    }


@router.post("/admin/roles")
def admin_create_role(payload: RoleReq, _auth=Depends(require_action("roles.manage"))):
    db = load_auth_db()
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    code = str(payload.code or "").strip().lower()
    if not code:
        raise HTTPException(status_code=400, detail="ROLE_CODE_REQUIRED")
    if any(str((role or {}).get("code") or "").strip().lower() == code for role in roles.values() if isinstance(role, dict)):
        raise HTTPException(status_code=409, detail="ROLE_CODE_EXISTS")
    role_id = f"role_{code}"
    roles[role_id] = {
        "id": role_id,
        "code": code,
        "name": str(payload.name or "").strip(),
        "description": str(payload.description or "").strip(),
        "pages": [str(x).strip() for x in payload.pages if str(x).strip()],
        "actions": [str(x).strip() for x in payload.actions if str(x).strip()],
        "is_system": False,
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    db["roles"] = roles
    save_auth_db(db)
    return {"ok": True, "role": _role_public(roles[role_id])}


@router.put("/admin/roles/{role_id}")
def admin_update_role(role_id: str, payload: RoleReq, _auth=Depends(require_action("roles.manage"))):
    db = load_auth_db()
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    role = roles.get(role_id)
    if not isinstance(role, dict):
        raise HTTPException(status_code=404, detail="ROLE_NOT_FOUND")
    _assert_role_manageable(_auth, role)
    if bool(role.get("is_system")) and str(role.get("code") or "") == "owner":
        payload.code = "owner"
    code = str(payload.code or "").strip().lower()
    if not code:
        raise HTTPException(status_code=400, detail="ROLE_CODE_REQUIRED")
    for rid, row in roles.items():
        if rid == role_id or not isinstance(row, dict):
            continue
        if str(row.get("code") or "").strip().lower() == code:
            raise HTTPException(status_code=409, detail="ROLE_CODE_EXISTS")
    role.update(
        {
            "code": code,
            "name": str(payload.name or "").strip(),
            "description": str(payload.description or "").strip(),
            "pages": [str(x).strip() for x in payload.pages if str(x).strip()],
            "actions": [str(x).strip() for x in payload.actions if str(x).strip()],
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
    )
    roles[role_id] = role
    db["roles"] = roles
    save_auth_db(db)
    return {"ok": True, "role": _role_public(role)}


@router.get("/admin/users")
def admin_users(_auth=Depends(require_action("users.manage"))):
    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    visible_roles = _visible_roles(_auth, roles)
    visible_users = _visible_users(_auth, users, roles)
    return {
        "ok": True,
        "users": [_user_public(user, visible_roles) for user in visible_users.values() if isinstance(user, dict)],
        "roles": [_role_public(role) for role in visible_roles.values() if isinstance(role, dict)],
    }


@router.get("/admin/login-events")
def admin_login_events(_auth=Depends(require_action("users.manage"))):
    events = recent_login_events(120)
    if _auth_is_owner(_auth):
      return {"ok": True, "events": events}
    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    visible_users = _visible_users(_auth, users, roles)
    visible_ids = {str((user or {}).get("id") or "") for user in visible_users.values() if isinstance(user, dict)}
    visible_logins = {str((user or {}).get("login") or "") for user in visible_users.values() if isinstance(user, dict)}
    filtered = [event for event in events if str(event.get("user_id") or "") in visible_ids or str(event.get("login") or "") in visible_logins]
    return {"ok": True, "events": filtered}


@router.post("/admin/users")
def admin_create_user(payload: UserReq, _auth=Depends(require_action("users.manage"))):
    from app.core.auth import _hash_password  # type: ignore

    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    visible_roles = _visible_roles(_auth, roles)
    login = str(payload.login or "").strip().lower()
    email = str(payload.email or "").strip().lower()
    if not login:
        raise HTTPException(status_code=400, detail="USER_LOGIN_REQUIRED")
    if not str(payload.password or "").strip():
        raise HTTPException(status_code=400, detail="USER_PASSWORD_REQUIRED")
    if any(str((user or {}).get("login") or "").strip().lower() == login for user in users.values() if isinstance(user, dict)):
        raise HTTPException(status_code=409, detail="USER_LOGIN_EXISTS")
    if email and any(str((user or {}).get("email") or "").strip().lower() == email for user in users.values() if isinstance(user, dict)):
        raise HTTPException(status_code=409, detail="USER_EMAIL_EXISTS")
    role_ids = [rid for rid in payload.role_ids if isinstance(visible_roles.get(rid), dict)]
    password_hash, password_salt = _hash_password(str(payload.password))
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    user_id = f"user_{__import__('secrets').token_hex(6)}"
    user = {
        "id": user_id,
        "login": login,
        "email": email,
        "name": str(payload.name or "").strip(),
        "role_ids": role_ids,
        "is_active": bool(payload.is_active),
        "password_hash": password_hash,
        "password_salt": password_salt,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    users[user_id] = user
    db["users"] = users
    save_auth_db(db)
    return {"ok": True, "user": _user_public(user, visible_roles)}


@router.put("/admin/users/{user_id}")
def admin_update_user(user_id: str, payload: UserReq, _auth=Depends(require_action("users.manage"))):
    from app.core.auth import _hash_password  # type: ignore

    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    user = users.get(user_id)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    _assert_user_manageable(_auth, user, roles)
    visible_roles = _visible_roles(_auth, roles)
    login = str(payload.login or "").strip().lower()
    email = str(payload.email or "").strip().lower()
    if not login:
        raise HTTPException(status_code=400, detail="USER_LOGIN_REQUIRED")
    for uid, row in users.items():
        if uid == user_id or not isinstance(row, dict):
            continue
        if str(row.get("login") or "").strip().lower() == login:
            raise HTTPException(status_code=409, detail="USER_LOGIN_EXISTS")
        if email and str(row.get("email") or "").strip().lower() == email:
            raise HTTPException(status_code=409, detail="USER_EMAIL_EXISTS")
    role_ids = [rid for rid in payload.role_ids if isinstance(visible_roles.get(rid), dict)]
    user.update(
        {
            "login": login,
            "email": email,
            "name": str(payload.name or "").strip(),
            "role_ids": role_ids,
            "is_active": bool(payload.is_active),
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
    )
    if str(payload.password or "").strip():
        password_hash, password_salt = _hash_password(str(payload.password))
        user["password_hash"] = password_hash
        user["password_salt"] = password_salt
    users[user_id] = user
    db["users"] = users
    save_auth_db(db)
    return {"ok": True, "user": _user_public(user, visible_roles)}


@router.post("/admin/users/{user_id}/reset-password")
def admin_user_reset_password(user_id: str, payload: ResetPasswordReq, _auth=Depends(require_action("users.manage"))):
    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    user = users.get(user_id)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    _assert_user_manageable(_auth, user, roles)
    try:
        result = admin_reset_password(user_id, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    visible_roles = _visible_roles(_auth, roles)
    return {
        "ok": True,
        "user": _user_public(result["user"], visible_roles),
        "password": result["password"],
    }


def bootstrap_owner_credentials(login: str, password: str, name: str = "Владелец", email: str = "") -> Dict[str, Any]:
    return ensure_owner_account(login=login, password=password, name=name, email=email)
