from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import Request

from app.core.control_plane import can_access_organization, ensure_user_membership_context, load_user_session_context
from app.core.json_store import DATA_DIR, read_doc, write_doc

AUTH_BASE_PATH = DATA_DIR / "auth" / "access.json"
AUTH_SESSIONS_PATH = DATA_DIR / "auth" / "sessions.json"
AUTH_EVENTS_PATH = DATA_DIR / "auth" / "login_events.json"
SESSION_COOKIE = "pim_session"
SESSION_TTL_DAYS = 30
SESSION_TOUCH_INTERVAL_SECONDS = 600

PAGE_CATALOG: List[Dict[str, str]] = [
    {"code": "dashboard", "title": "Дашборд"},
    {"code": "catalog", "title": "Каталог"},
    {"code": "products", "title": "Товары"},
    {"code": "product_groups", "title": "Группы товаров"},
    {"code": "catalog_import", "title": "Импорт каталога"},
    {"code": "catalog_export", "title": "Экспорт каталога"},
    {"code": "templates", "title": "Мастер-шаблоны"},
    {"code": "dictionaries", "title": "Параметры и словари"},
    {"code": "sources_mapping", "title": "Источники"},
    {"code": "connectors_status", "title": "Коннекторы"},
    {"code": "infographics", "title": "Инфографика"},
    {"code": "stats_card_quality", "title": "Качество карточек"},
    {"code": "stats_marketplace_quality", "title": "Качество на маркетплейсах"},
    {"code": "admin_access", "title": "Пользователи и роли"},
]

ACTION_CATALOG: List[Dict[str, str]] = [
    {"code": "users.manage", "title": "Управление пользователями"},
    {"code": "roles.manage", "title": "Управление ролями"},
    {"code": "products.manage", "title": "Изменение товаров"},
    {"code": "templates.manage", "title": "Изменение мастер-шаблонов"},
    {"code": "dictionaries.manage", "title": "Изменение словарей"},
    {"code": "sources.manage", "title": "Изменение маппинга источников"},
    {"code": "connectors.manage", "title": "Изменение коннекторов"},
    {"code": "media.manage", "title": "Изменение медиа"},
    {"code": "stats.view", "title": "Просмотр статистики"},
]

SYSTEM_ROLES: List[Dict[str, Any]] = [
    {
        "id": "role_owner",
        "code": "owner",
        "name": "Владелец",
        "description": "Полный доступ ко всем страницам и действиям.",
        "pages": ["*"],
        "actions": ["*"],
    },
    {
        "id": "role_admin",
        "code": "admin",
        "name": "Администратор",
        "description": "Управляет контентом, коннекторами и пользователями.",
        "pages": ["*"],
        "actions": ["users.manage", "roles.manage", "products.manage", "templates.manage", "dictionaries.manage", "sources.manage", "connectors.manage", "media.manage", "stats.view"],
    },
    {
        "id": "role_editor",
        "code": "editor",
        "name": "Контент-менеджер",
        "description": "Работает с товарами, шаблонами и источниками.",
        "pages": [
            "dashboard",
            "catalog",
            "products",
            "product_groups",
            "catalog_import",
            "catalog_export",
            "templates",
            "dictionaries",
            "sources_mapping",
            "connectors_status",
            "infographics",
            "stats_card_quality",
            "stats_marketplace_quality",
        ],
        "actions": ["products.manage", "templates.manage", "dictionaries.manage", "sources.manage", "connectors.manage", "media.manage", "stats.view"],
    },
    {
        "id": "role_viewer",
        "code": "viewer",
        "name": "Наблюдатель",
        "description": "Только просмотр основных страниц.",
        "pages": [
            "dashboard",
            "catalog",
            "products",
            "product_groups",
            "templates",
            "dictionaries",
            "sources_mapping",
            "connectors_status",
            "stats_card_quality",
            "stats_marketplace_quality",
        ],
        "actions": ["stats.view"],
    },
]

DEFAULT_AUTH_BASE_DB: Dict[str, Any] = {
    "version": 1,
    "roles": {},
    "users": {},
}

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/session",
    "/api/auth/logout",
    "/api/platform/register",
    "/api/platform/invites/accept",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _clone(v: Any) -> Any:
    import json

    return json.loads(json.dumps(v))


def _load_auth_base() -> Dict[str, Any]:
    db = read_doc(AUTH_BASE_PATH, default=_clone(DEFAULT_AUTH_BASE_DB))
    if not isinstance(db, dict):
        db = _clone(DEFAULT_AUTH_BASE_DB)
    if not isinstance(db.get("roles"), dict):
        db["roles"] = {}
    if not isinstance(db.get("users"), dict):
        db["users"] = {}
    return db


def load_auth_base_db() -> Dict[str, Any]:
    db = _load_auth_base()
    return _ensure_system_roles(db)


def _save_auth_base(db: Dict[str, Any]) -> None:
    payload = {
        "version": db.get("version", 1),
        "roles": db.get("roles") if isinstance(db.get("roles"), dict) else {},
        "users": db.get("users") if isinstance(db.get("users"), dict) else {},
    }
    write_doc(AUTH_BASE_PATH, payload)


def _load_auth_sessions() -> Dict[str, Any]:
    doc = read_doc(AUTH_SESSIONS_PATH, default={"sessions": {}})
    if not isinstance(doc, dict):
        return {}
    sessions = doc.get("sessions")
    return sessions if isinstance(sessions, dict) else {}


def _save_auth_sessions(sessions: Dict[str, Any]) -> None:
    write_doc(AUTH_SESSIONS_PATH, {"sessions": sessions if isinstance(sessions, dict) else {}})


def _load_auth_login_events() -> List[Dict[str, Any]]:
    doc = read_doc(AUTH_EVENTS_PATH, default={"login_events": []})
    if not isinstance(doc, dict):
        return []
    rows = doc.get("login_events")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _save_auth_login_events(events: List[Dict[str, Any]]) -> None:
    rows = [row for row in events if isinstance(row, dict)]
    write_doc(AUTH_EVENTS_PATH, {"login_events": rows[-300:]})


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_login(value: Any) -> str:
    return _normalize_text(value).lower()


def _hash_password(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return hashed.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    calc_hash, _ = _hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(calc_hash, str(password_hash or ""))


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ensure_system_roles(db: Dict[str, Any]) -> Dict[str, Any]:
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    by_code: Dict[str, Dict[str, Any]] = {}
    for role in roles.values():
        if isinstance(role, dict):
            code = _normalize_text(role.get("code"))
            if code:
                by_code[code] = role
    for row in SYSTEM_ROLES:
        existing = by_code.get(row["code"])
        if existing:
            existing["name"] = row["name"]
            existing["description"] = row["description"]
            existing["is_system"] = True
            existing.setdefault("pages", _clone(row["pages"]))
            existing.setdefault("actions", _clone(row["actions"]))
            continue
        roles[row["id"]] = {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "pages": _clone(row["pages"]),
            "actions": _clone(row["actions"]),
            "is_system": True,
            "created_at": _iso(),
            "updated_at": _iso(),
        }
    db["roles"] = roles
    return db


def load_auth_db() -> Dict[str, Any]:
    db = load_auth_base_db()
    db["sessions"] = _load_auth_sessions()
    db["login_events"] = _load_auth_login_events()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    changed = False
    for uid, user in users.items():
        if not isinstance(user, dict):
            continue
        login = _normalize_login(user.get("login"))
        email = _normalize_text(user.get("email")).lower()
        if not login:
            fallback = email or _normalize_login(user.get("name")) or str(uid)
            user["login"] = fallback
            changed = True
        if "email" not in user:
            user["email"] = ""
            changed = True
    if changed:
        db["users"] = users
        _save_auth_base(db)
    return db


def save_auth_db(db: Dict[str, Any]) -> None:
    _save_auth_base(db)
    _save_auth_sessions(db.get("sessions") if isinstance(db.get("sessions"), dict) else {})
    _save_auth_login_events(db.get("login_events") if isinstance(db.get("login_events"), list) else [])


def list_permission_catalog() -> Dict[str, Any]:
    return {"pages": _clone(PAGE_CATALOG), "actions": _clone(ACTION_CATALOG)}


def find_role_by_code(db: Dict[str, Any], code: str) -> Optional[Dict[str, Any]]:
    code_s = _normalize_text(code)
    if not code_s:
        return None
    roles = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    for role in roles.values():
        if isinstance(role, dict) and _normalize_text(role.get("code")) == code_s:
            return role
    return None


def _effective_codes(roles: Iterable[Dict[str, Any]], field: str) -> Set[str]:
    out: Set[str] = set()
    for role in roles:
        values = role.get(field) if isinstance(role.get(field), list) else []
        for item in values:
            code = _normalize_text(item)
            if code:
                out.add(code)
    return out


def session_payload(user: Dict[str, Any], roles: List[Dict[str, Any]], session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pages = sorted(_effective_codes(roles, "pages"))
    actions = sorted(_effective_codes(roles, "actions"))
    current_org_id = _normalize_text((session or {}).get("current_organization_id"))
    org_ctx = load_user_session_context(user, roles, current_organization_id=current_org_id)
    return {
        "authenticated": True,
        "user": {
            "id": user.get("id"),
            "login": user.get("login"),
            "email": user.get("email"),
            "name": user.get("name"),
            "is_active": bool(user.get("is_active", True)),
            "role_ids": user.get("role_ids") or [],
            "pages": pages,
            "actions": actions,
        },
        "platform_roles": org_ctx.get("platform_roles") or [],
        "organizations": org_ctx.get("organizations") or [],
        "current_organization": org_ctx.get("current_organization"),
        "effective_access": {
            "pages": pages,
            "actions": actions,
        },
        "flags": org_ctx.get("flags") or {"is_developer": False},
        "roles": [
            {
                "id": role.get("id"),
                "code": role.get("code"),
                "name": role.get("name"),
                "description": role.get("description"),
                "pages": role.get("pages") or [],
                "actions": role.get("actions") or [],
                "is_system": bool(role.get("is_system")),
            }
            for role in roles
        ],
        "catalog": list_permission_catalog(),
    }


@dataclass
class AuthContext:
    user: Optional[Dict[str, Any]]
    roles: List[Dict[str, Any]]
    pages: Set[str]
    actions: Set[str]
    session_id: Optional[str] = None
    session: Optional[Dict[str, Any]] = None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None


def _resolve_roles(db: Dict[str, Any], role_ids: Iterable[Any]) -> List[Dict[str, Any]]:
    roles_map = db.get("roles") if isinstance(db.get("roles"), dict) else {}
    out: List[Dict[str, Any]] = []
    for rid in role_ids:
        role = roles_map.get(str(rid))
        if isinstance(role, dict):
            out.append(role)
    return out


def build_auth_context(
    db: Dict[str, Any],
    user: Optional[Dict[str, Any]],
    session_id: Optional[str] = None,
    session: Optional[Dict[str, Any]] = None,
) -> AuthContext:
    if not isinstance(user, dict):
        return AuthContext(None, [], set(), set(), session_id=session_id, session=session)
    roles = _resolve_roles(db, user.get("role_ids") or [])
    return AuthContext(
        user=user,
        roles=roles,
        pages=_effective_codes(roles, "pages"),
        actions=_effective_codes(roles, "actions"),
        session_id=session_id,
        session=session,
    )


def has_page(auth: AuthContext, page_code: str) -> bool:
    if not auth.user:
        return False
    return "*" in auth.pages or page_code in auth.pages


def has_action(auth: AuthContext, action_code: str) -> bool:
    if not auth.user:
        return False
    return "*" in auth.actions or action_code in auth.actions


def authenticate(login: str, password: str) -> Optional[Dict[str, Any]]:
    db = load_auth_base_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    login_s = _normalize_login(login)
    for user in users.values():
        if not isinstance(user, dict):
            continue
        user_login = _normalize_login(user.get("login"))
        user_email = _normalize_text(user.get("email")).lower()
        if user_login != login_s and user_email != login_s:
            continue
        if not bool(user.get("is_active", True)):
            return None
        if verify_password(password, str(user.get("password_hash") or ""), str(user.get("password_salt") or "")):
            return user
        return None
    return None


def find_user_by_login_or_email(login_or_email: str) -> Optional[Dict[str, Any]]:
    db = load_auth_base_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    target = _normalize_login(login_or_email)
    for user in users.values():
        if not isinstance(user, dict):
            continue
        if _normalize_login(user.get("login")) == target or _normalize_text(user.get("email")).lower() == target:
            return user
    return None


def _append_login_event(
    db: Dict[str, Any],
    *,
    login: str,
    user_id: str = "",
    user_name: str = "",
    status: str,
    ip: str = "",
    user_agent: str = "",
) -> None:
    events = db.get("login_events") if isinstance(db.get("login_events"), list) else []
    events.append(
        {
            "id": f"evt_{secrets.token_hex(8)}",
            "at": _iso(),
            "login": _normalize_text(login),
            "user_id": _normalize_text(user_id),
            "user_name": _normalize_text(user_name),
            "status": _normalize_text(status) or "unknown",
            "ip": _normalize_text(ip),
            "user_agent": _normalize_text(user_agent),
        }
    )
    db["login_events"] = events[-300:]


def record_login_failure(login: str, ip: str = "", user_agent: str = "") -> None:
    events = _load_auth_login_events()
    db = {"login_events": events}
    _append_login_event(db, login=login, status="failed", ip=ip, user_agent=user_agent)
    _save_auth_login_events(db.get("login_events") if isinstance(db.get("login_events"), list) else [])


def record_login_success(user_id: str, ip: str = "", user_agent: str = "") -> Optional[Dict[str, Any]]:
    db = _load_auth_base()
    db = _ensure_system_roles(db)
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    user = users.get(str(user_id or ""))
    if not isinstance(user, dict):
        return None
    user["last_login_at"] = _iso()
    user["last_login_ip"] = _normalize_text(ip)
    user["last_user_agent"] = _normalize_text(user_agent)
    user["updated_at"] = _iso()
    users[str(user_id)] = user
    db["users"] = users
    _save_auth_base(db)
    events_db = {"login_events": _load_auth_login_events()}
    _append_login_event(
        events_db,
        login=_normalize_text(user.get("login")) or _normalize_text(user.get("email")),
        user_id=str(user_id),
        user_name=_normalize_text(user.get("name")),
        status="success",
        ip=ip,
        user_agent=user_agent,
    )
    _save_auth_login_events(events_db.get("login_events") if isinstance(events_db.get("login_events"), list) else [])
    return user


def recent_login_events(limit: int = 100) -> List[Dict[str, Any]]:
    events = _load_auth_login_events()
    rows = [row for row in events if isinstance(row, dict)]
    return list(reversed(rows[-max(1, min(limit, 300)) :]))


def change_password(user_id: str, current_password: str, new_password: str) -> Dict[str, Any]:
    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    user = users.get(str(user_id or ""))
    if not isinstance(user, dict):
        raise ValueError("USER_NOT_FOUND")
    if not verify_password(current_password, str(user.get("password_hash") or ""), str(user.get("password_salt") or "")):
        raise ValueError("INVALID_CURRENT_PASSWORD")
    password_hash, password_salt = _hash_password(new_password)
    user["password_hash"] = password_hash
    user["password_salt"] = password_salt
    user["updated_at"] = _iso()
    users[str(user_id)] = user
    db["users"] = users
    save_auth_db(db)
    return user


def admin_reset_password(user_id: str, new_password: Optional[str] = None) -> Dict[str, Any]:
    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    user = users.get(str(user_id or ""))
    if not isinstance(user, dict):
        raise ValueError("USER_NOT_FOUND")
    password_value = _normalize_text(new_password) or secrets.token_urlsafe(10)
    password_hash, password_salt = _hash_password(password_value)
    user["password_hash"] = password_hash
    user["password_salt"] = password_salt
    user["updated_at"] = _iso()
    users[str(user_id)] = user
    db["users"] = users
    save_auth_db(db)
    return {"user": user, "password": password_value}


def create_session(user_id: str, current_organization_id: Optional[str] = None) -> str:
    sessions = _load_auth_sessions()
    token = secrets.token_urlsafe(32)
    token_hash = _hash_session_token(token)
    sessions[token_hash] = {
        "id": token_hash,
        "user_id": user_id,
        "current_organization_id": _normalize_text(current_organization_id),
        "created_at": _iso(),
        "last_seen_at": _iso(),
        "expires_at": _iso(_now() + timedelta(days=SESSION_TTL_DAYS)),
    }
    _save_auth_sessions(sessions)
    return token


def drop_session(token: str) -> None:
    sessions = _load_auth_sessions()
    token_hash = _hash_session_token(token)
    if token_hash in sessions:
        sessions.pop(token_hash, None)
        _save_auth_sessions(sessions)


def _should_touch_session(last_seen_at: str) -> bool:
    if not _normalize_text(last_seen_at):
        return True
    try:
        last_seen = datetime.fromisoformat(last_seen_at)
    except Exception:
        return True
    return (_now() - last_seen).total_seconds() >= SESSION_TOUCH_INTERVAL_SECONDS


def auth_from_request(request: Request) -> AuthContext:
    token = _normalize_text(request.cookies.get(SESSION_COOKIE))
    if not token:
        return AuthContext(None, [], set(), set())
    db = _load_auth_base()
    db = _ensure_system_roles(db)
    sessions = _load_auth_sessions()
    token_hash = _hash_session_token(token)
    session = sessions.get(token_hash)
    if not isinstance(session, dict):
        return AuthContext(None, [], set(), set())
    expires_at = _normalize_text(session.get("expires_at"))
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at)
            if expires <= _now():
                sessions.pop(token_hash, None)
                _save_auth_sessions(sessions)
                return AuthContext(None, [], set(), set())
        except Exception:
            sessions.pop(token_hash, None)
            _save_auth_sessions(sessions)
            return AuthContext(None, [], set(), set())
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    user = users.get(str(session.get("user_id") or ""))
    if not isinstance(user, dict) or not bool(user.get("is_active", True)):
        return AuthContext(None, [], set(), set())
    if _should_touch_session(str(session.get("last_seen_at") or "")):
        session["last_seen_at"] = _iso()
        sessions[token_hash] = session
        _save_auth_sessions(sessions)
    return build_auth_context(db, user, session_id=token_hash, session=session)


def ensure_owner_account(login: str, password: str, name: str = "Владелец", email: str = "") -> Dict[str, Any]:
    return ensure_user_account(login=login, password=password, name=name, email=email, role_code="owner")


def ensure_user_account(
    *,
    login: str,
    password: str,
    name: str,
    email: str = "",
    role_code: str = "viewer",
) -> Dict[str, Any]:
    db = load_auth_db()
    users = db.get("users") if isinstance(db.get("users"), dict) else {}
    role = find_role_by_code(db, role_code)
    if not role:
        db = _ensure_system_roles(db)
        role = find_role_by_code(db, role_code)
    assert role is not None
    login_s = _normalize_login(login)
    email_s = _normalize_text(email).lower()
    existing_user: Optional[Dict[str, Any]] = None
    existing_id = ""
    for uid, user in users.items():
        if not isinstance(user, dict):
            continue
        if _normalize_login(user.get("login")) == login_s:
            existing_user = user
            existing_id = uid
            break
        if email_s and _normalize_text(user.get("email")).lower() == email_s:
            existing_user = user
            existing_id = uid
            break
    password_hash, password_salt = _hash_password(password)
    now = _iso()
    if existing_user:
        existing_user.update(
            {
                "login": login_s,
                "email": email_s,
                "name": _normalize_text(name) or login_s or email_s,
                "password_hash": password_hash,
                "password_salt": password_salt,
                "role_ids": [role["id"]],
                "is_active": True,
                "updated_at": now,
            }
        )
        users[existing_id] = existing_user
        db["users"] = users
        save_auth_db(db)
        ensure_user_membership_context(existing_user, [role])
        return existing_user
    user_id = f"user_{secrets.token_hex(6)}"
    user = {
        "id": user_id,
        "login": login_s,
        "email": email_s,
        "name": _normalize_text(name) or login_s or email_s,
        "password_hash": password_hash,
        "password_salt": password_salt,
        "role_ids": [role["id"]],
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    users[user_id] = user
    db["users"] = users
    save_auth_db(db)
    ensure_user_membership_context(user, [role])
    return user


def update_session_current_organization(auth: AuthContext, organization_id: str) -> Dict[str, Any]:
    if not auth.user or not auth.session_id:
        raise ValueError("AUTH_REQUIRED")
    target = _normalize_text(organization_id)
    if not target:
        raise ValueError("ORGANIZATION_REQUIRED")
    if not can_access_organization(auth.user, auth.roles, target):
        raise ValueError("ORGANIZATION_FORBIDDEN")
    sessions = _load_auth_sessions()
    session = sessions.get(str(auth.session_id))
    if not isinstance(session, dict):
        raise ValueError("SESSION_NOT_FOUND")
    session["current_organization_id"] = target
    session["last_seen_at"] = _iso()
    sessions[str(auth.session_id)] = session
    _save_auth_sessions(sessions)
    return session


def auth_cookie_secure() -> bool:
    raw = _normalize_text(os.getenv("AUTH_COOKIE_SECURE") or "")
    if raw:
        return raw in {"1", "true", "yes", "on"}
    return False
