from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.core.json_store import JsonStoreError, _is_retryable_pg_error, _pg_connect, _reset_pg_connection

DEFAULT_ORGANIZATION_ID = "org_default"
DEFAULT_ORGANIZATION_SLUG = "default"
DEFAULT_ORGANIZATION_NAME = "Global Trade"
INVITE_TTL_DAYS = 7
_CONTROL_PLANE_FOUNDATION_CACHE_TTL_SECONDS = 30.0
_MEMBERSHIP_CONTEXT_CACHE_TTL_SECONDS = 30.0
_CONTROL_PLANE_FOUNDATION_STATE: Dict[str, float | bool] = {"ready": False, "ts": 0.0}
_CONTROL_PLANE_FOUNDATION_LOCK = threading.Lock()
_MEMBERSHIP_CONTEXT_STATE: Dict[str, float] = {}
_MEMBERSHIP_CONTEXT_LOCK = threading.Lock()


def _with_pg_retry(fn):
    try:
        return fn()
    except Exception as exc:
        if not _is_retryable_pg_error(exc):
            raise
        _reset_pg_connection()
        return fn()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_email(value: Any) -> str:
    return _normalize_text(value).lower()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _normalize_role_codes(role_codes: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for role in role_codes:
        code = _normalize_text(role).lower()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _org_role_from_legacy_roles(role_codes: Iterable[Any]) -> str:
    codes = set(_normalize_role_codes(role_codes))
    if "owner" in codes:
        return "org_owner"
    if "admin" in codes:
        return "org_admin"
    if "editor" in codes:
        return "org_editor"
    return "org_viewer"


def _org_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _normalize_text(row.get("id")),
        "slug": _normalize_text(row.get("slug")),
        "name": _normalize_text(row.get("name")),
        "status": _normalize_text(row.get("status")) or "active",
        "membership_role": _normalize_text(row.get("membership_role")) or None,
    }


def _extract_rows(cur: Any) -> List[Dict[str, Any]]:
    cols = [str((item or [None])[0] or "") for item in (cur.description or [])]
    rows: List[Dict[str, Any]] = []
    for raw in cur.fetchall() or []:
        if isinstance(raw, dict):
            rows.append({str(k): raw[k] for k in raw.keys()})
            continue
        rows.append({cols[idx]: raw[idx] for idx in range(min(len(cols), len(raw)))})
    return rows


def _ensure_control_plane_tables() -> bool:
    now = time.monotonic()
    cached_ready = bool(_CONTROL_PLANE_FOUNDATION_STATE.get("ready"))
    cached_ts = float(_CONTROL_PLANE_FOUNDATION_STATE.get("ts") or 0.0)
    if cached_ready and now - cached_ts < _CONTROL_PLANE_FOUNDATION_CACHE_TTL_SECONDS:
        return True

    def _run() -> bool:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  login TEXT NOT NULL DEFAULT '',
                  email TEXT NOT NULL,
                  password_hash TEXT NOT NULL DEFAULT '',
                  password_salt TEXT NOT NULL DEFAULT '',
                  name TEXT NOT NULL,
                  role_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                  is_active BOOLEAN NOT NULL DEFAULT TRUE,
                  status TEXT NOT NULL DEFAULT 'active',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  last_login_at TIMESTAMPTZ NULL,
                  last_login_ip TEXT NULL,
                  last_user_agent TEXT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_login
                  ON users ((lower(login)))
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_email_non_empty
                  ON users ((lower(email))) WHERE email <> ''
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS roles (
                  id TEXT PRIMARY KEY,
                  code TEXT NOT NULL UNIQUE,
                  name TEXT NOT NULL,
                  description TEXT NULL,
                  pages JSONB NOT NULL DEFAULT '[]'::jsonb,
                  actions JSONB NOT NULL DEFAULT '[]'::jsonb,
                  is_system BOOLEAN NOT NULL DEFAULT FALSE,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                  id TEXT PRIMARY KEY,
                  slug TEXT NOT NULL,
                  name TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active',
                  tenant_status TEXT NULL,
                  provisioning_error TEXT NULL,
                  schema_version TEXT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_lower_slug
                  ON organizations ((lower(slug)))
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS organization_members (
                  id TEXT PRIMARY KEY,
                  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  org_role_code TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_members_unique
                  ON organization_members (organization_id, user_id)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS organization_invites (
                  id TEXT PRIMARY KEY,
                  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                  email TEXT NOT NULL,
                  org_role_code TEXT NOT NULL,
                  token_hash TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  expires_at TIMESTAMPTZ NOT NULL,
                  created_by_user_id TEXT NOT NULL REFERENCES users(id),
                  accepted_by_user_id TEXT NULL REFERENCES users(id),
                  accepted_at TIMESTAMPTZ NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_invites_token_hash
                  ON organization_invites (token_hash)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_organization_invites_org_email
                  ON organization_invites (organization_id, lower(email))
                """
            )
            cur.execute(
                """
                INSERT INTO organizations (id, slug, name, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'active', NOW(), NOW())
                ON CONFLICT (id) DO UPDATE
                SET slug = EXCLUDED.slug,
                    name = EXCLUDED.name,
                    updated_at = NOW()
                """,
                (DEFAULT_ORGANIZATION_ID, DEFAULT_ORGANIZATION_SLUG, DEFAULT_ORGANIZATION_NAME),
            )
        return True

    try:
        with _CONTROL_PLANE_FOUNDATION_LOCK:
            now_locked = time.monotonic()
            cached_ready_locked = bool(_CONTROL_PLANE_FOUNDATION_STATE.get("ready"))
            cached_ts_locked = float(_CONTROL_PLANE_FOUNDATION_STATE.get("ts") or 0.0)
            if cached_ready_locked and now_locked - cached_ts_locked < _CONTROL_PLANE_FOUNDATION_CACHE_TTL_SECONDS:
                return True
            ready = bool(_with_pg_retry(_run))
            _CONTROL_PLANE_FOUNDATION_STATE["ready"] = ready
            _CONTROL_PLANE_FOUNDATION_STATE["ts"] = now_locked
            return ready
    except JsonStoreError:
        return False
    except Exception:
        return False


def ensure_control_plane_foundation() -> bool:
    return _ensure_control_plane_tables()


def _ensure_platform_user(conn: Any, user: Dict[str, Any]) -> str:
    user_id = _normalize_text(user.get("id")) or f"user_{secrets.token_hex(6)}"
    login = _normalize_text(user.get("login")).lower()
    email = _normalize_email(user.get("email")) or f"{_normalize_text(user.get('login')) or user_id}@local.invalid"
    name = _normalize_text(user.get("name")) or _normalize_text(user.get("login")) or email
    password_hash = _normalize_text(user.get("password_hash"))
    password_salt = _normalize_text(user.get("password_salt"))
    role_ids = [str(x) for x in (user.get("role_ids") or []) if str(x).strip()]
    last_login_at = user.get("last_login_at")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (
              id, login, email, password_hash, password_salt, name, role_ids, is_active, status, created_at, updated_at, last_login_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, TRUE, 'active', NOW(), NOW(), %s)
            ON CONFLICT (id) DO UPDATE
            SET login = COALESCE(NULLIF(EXCLUDED.login, ''), users.login),
                email = EXCLUDED.email,
                password_hash = COALESCE(NULLIF(EXCLUDED.password_hash, ''), users.password_hash),
                password_salt = COALESCE(NULLIF(EXCLUDED.password_salt, ''), users.password_salt),
                name = EXCLUDED.name,
                role_ids = EXCLUDED.role_ids,
                is_active = TRUE,
                status = 'active',
                updated_at = NOW(),
                last_login_at = COALESCE(EXCLUDED.last_login_at, users.last_login_at)
            """,
            (user_id, login, email, password_hash, password_salt, name, json.dumps(role_ids, ensure_ascii=False), last_login_at),
        )
    return user_id


def ensure_user_membership_context(user: Optional[Dict[str, Any]], legacy_roles: Iterable[Dict[str, Any]]) -> bool:
    if not isinstance(user, dict):
        return False
    if not ensure_control_plane_foundation():
        return False

    role_codes = [_normalize_text((role or {}).get("code")).lower() for role in legacy_roles if isinstance(role, dict)]
    user_cache_key = f"{_normalize_text(user.get('id'))}:{_org_role_from_legacy_roles(role_codes)}"
    now = time.monotonic()
    with _MEMBERSHIP_CONTEXT_LOCK:
        cached_ts = float(_MEMBERSHIP_CONTEXT_STATE.get(user_cache_key) or 0.0)
        if cached_ts and now - cached_ts < _MEMBERSHIP_CONTEXT_CACHE_TTL_SECONDS:
            return True

    def _run() -> bool:
        conn, _, _ = _pg_connect()
        user_id = _ensure_platform_user(conn, user)
        org_role_code = _org_role_from_legacy_roles(role_codes)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM organization_members
                WHERE organization_id = %s AND user_id = %s
                """,
                (DEFAULT_ORGANIZATION_ID, user_id),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO organization_members (
                      id, organization_id, user_id, org_role_code, status, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, 'active', NOW(), NOW())
                    """,
                    (f"org_member_{secrets.token_hex(6)}", DEFAULT_ORGANIZATION_ID, user_id, org_role_code),
                )
        return True

    try:
        ready = bool(_with_pg_retry(_run))
        if ready:
            with _MEMBERSHIP_CONTEXT_LOCK:
                _MEMBERSHIP_CONTEXT_STATE[user_cache_key] = time.monotonic()
        return ready
    except Exception:
        return False


def load_user_session_context(
    user: Optional[Dict[str, Any]],
    legacy_roles: Iterable[Dict[str, Any]],
    current_organization_id: Optional[str] = None,
) -> Dict[str, Any]:
    legacy_role_codes = [_normalize_text((role or {}).get("code")).lower() for role in legacy_roles if isinstance(role, dict)]
    default_org = {
        "id": DEFAULT_ORGANIZATION_ID,
        "slug": DEFAULT_ORGANIZATION_SLUG,
        "name": DEFAULT_ORGANIZATION_NAME,
        "status": "active",
        "membership_role": _org_role_from_legacy_roles(legacy_role_codes),
    }
    fallback = {
        "platform_roles": [],
        "organizations": [default_org] if isinstance(user, dict) else [],
        "current_organization": default_org if isinstance(user, dict) else None,
        "flags": {"is_developer": False},
    }
    if not isinstance(user, dict):
        return fallback
    if not ensure_user_membership_context(user, legacy_roles):
        return fallback

    user_id = _normalize_text(user.get("id"))

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, o.slug, o.name, o.status, om.org_role_code AS membership_role
                FROM organization_members om
                JOIN organizations o ON o.id = om.organization_id
                WHERE om.user_id = %s
                  AND om.status = 'active'
                  AND o.status <> 'deleted'
                ORDER BY lower(o.name), o.id
                """,
                (user_id,),
            )
            organizations = [_org_public(row) for row in _extract_rows(cur)]
        if not organizations:
            organizations = [default_org]
        current_org_id = _normalize_text(current_organization_id)
        current_org = next((row for row in organizations if row["id"] == current_org_id), None) or organizations[0]
        return {
            "platform_roles": [],
            "organizations": organizations,
            "current_organization": current_org,
            "flags": {"is_developer": False},
        }

    try:
        return _with_pg_retry(_run)
    except Exception:
        return fallback


def can_access_organization(
    user: Optional[Dict[str, Any]],
    legacy_roles: Iterable[Dict[str, Any]],
    organization_id: str,
) -> bool:
    target = _normalize_text(organization_id)
    if not target:
        return False
    ctx = load_user_session_context(user, legacy_roles, current_organization_id=target)
    return any(_normalize_text(row.get("id")) == target for row in (ctx.get("organizations") or []))


def _next_org_slug(conn: Any, organization_name: str) -> str:
    base = _normalize_text(organization_name).lower()
    base = "".join(ch if ch.isalnum() else "-" for ch in base)
    base = "-".join(part for part in base.split("-") if part).strip("-") or "organization"
    slug = base
    idx = 2
    with conn.cursor() as cur:
        while True:
            cur.execute("SELECT 1 FROM organizations WHERE lower(slug) = lower(%s)", (slug,))
            if cur.fetchone() is None:
                return slug
            slug = f"{base}-{idx}"
            idx += 1


def create_organization_with_owner(user: Dict[str, Any], organization_name: str) -> Dict[str, Any]:
    if not isinstance(user, dict):
        raise ValueError("USER_REQUIRED")
    if not ensure_control_plane_foundation():
        raise ValueError("CONTROL_PLANE_UNAVAILABLE")
    org_name = _normalize_text(organization_name)
    if not org_name:
        raise ValueError("ORGANIZATION_NAME_REQUIRED")

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        user_id = _ensure_platform_user(conn, user)
        org_id = f"org_{secrets.token_hex(6)}"
        org_slug = _next_org_slug(conn, org_name)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (id, slug, name, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'active', NOW(), NOW())
                """,
                (org_id, org_slug, org_name),
            )
            cur.execute(
                """
                INSERT INTO organization_members (
                  id, organization_id, user_id, org_role_code, status, created_at, updated_at
                )
                VALUES (%s, %s, %s, 'org_owner', 'active', NOW(), NOW())
                """,
                (f"org_member_{secrets.token_hex(6)}", org_id, user_id),
            )
        return {
            "id": org_id,
            "slug": org_slug,
            "name": org_name,
            "status": "active",
            "membership_role": "org_owner",
        }

    return _with_pg_retry(_run)


def create_organization_invite(
    organization_id: str,
    email: str,
    org_role_code: str,
    created_by_user_id: str,
) -> Dict[str, Any]:
    if not ensure_control_plane_foundation():
        raise ValueError("CONTROL_PLANE_UNAVAILABLE")
    org_id = _normalize_text(organization_id)
    invite_email = _normalize_email(email)
    role_code = _normalize_text(org_role_code)
    creator_id = _normalize_text(created_by_user_id)
    if not org_id:
        raise ValueError("ORGANIZATION_REQUIRED")
    if not invite_email:
        raise ValueError("EMAIL_REQUIRED")
    if role_code not in {"org_owner", "org_admin", "org_editor", "org_viewer"}:
        raise ValueError("ORG_ROLE_INVALID")
    if not creator_id:
        raise ValueError("CREATOR_REQUIRED")

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_token)
        invite_id = f"invite_{secrets.token_hex(6)}"
        expires_at = (_now() + timedelta(days=INVITE_TTL_DAYS)).isoformat()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM organizations WHERE id = %s", (org_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("ORGANIZATION_NOT_FOUND")
            cur.execute(
                """
                INSERT INTO organization_invites (
                  id, organization_id, email, org_role_code, token_hash, status, expires_at, created_by_user_id, created_at
                )
                VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, NOW())
                """,
                (invite_id, org_id, invite_email, role_code, token_hash, expires_at, creator_id),
            )
        return {
            "id": invite_id,
            "organization_id": org_id,
            "email": invite_email,
            "org_role_code": role_code,
            "status": "pending",
            "expires_at": expires_at,
            "token": raw_token,
        }

    return _with_pg_retry(_run)


def accept_organization_invite(token: str, accepted_by_user_id: str) -> Dict[str, Any]:
    if not ensure_control_plane_foundation():
        raise ValueError("CONTROL_PLANE_UNAVAILABLE")
    raw_token = _normalize_text(token)
    user_id = _normalize_text(accepted_by_user_id)
    if not raw_token:
        raise ValueError("INVITE_TOKEN_REQUIRED")
    if not user_id:
        raise ValueError("USER_REQUIRED")

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        token_hash = _hash_token(raw_token)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, organization_id, email, org_role_code, status, expires_at
                FROM organization_invites
                WHERE token_hash = %s
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("INVITE_NOT_FOUND")
            invite_id, organization_id, email, org_role_code, status, expires_at = row
            if _normalize_text(status) != "pending":
                raise ValueError("INVITE_NOT_PENDING")
            if expires_at and expires_at <= _now():
                raise ValueError("INVITE_EXPIRED")
            cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            user_row = cur.fetchone()
            if not user_row:
                raise ValueError("USER_NOT_FOUND")
            if _normalize_email(user_row[1]) != _normalize_email(email):
                raise ValueError("INVITE_EMAIL_MISMATCH")
            cur.execute(
                """
                SELECT id
                FROM organization_members
                WHERE organization_id = %s AND user_id = %s
                """,
                (organization_id, user_id),
            )
            existing = cur.fetchone()
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO organization_members (
                      id, organization_id, user_id, org_role_code, status, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, 'active', NOW(), NOW())
                    """,
                    (f"org_member_{secrets.token_hex(6)}", organization_id, user_id, org_role_code),
                )
            cur.execute(
                """
                UPDATE organization_invites
                SET status = 'accepted',
                    accepted_by_user_id = %s,
                    accepted_at = NOW()
                WHERE id = %s
                """,
                (user_id, invite_id),
            )
            cur.execute("SELECT id, slug, name, status FROM organizations WHERE id = %s", (organization_id,))
            org_row = cur.fetchone()
        return {
            "invite_id": _normalize_text(invite_id),
            "organization": {
                "id": _normalize_text(org_row[0]),
                "slug": _normalize_text(org_row[1]),
                "name": _normalize_text(org_row[2]),
                "status": _normalize_text(org_row[3]),
                "membership_role": _normalize_text(org_role_code),
            },
        }

    return _with_pg_retry(_run)


def get_organization_provisioning_status(organization_id: str) -> Dict[str, Any]:
    if not ensure_control_plane_foundation():
        raise ValueError("CONTROL_PLANE_UNAVAILABLE")
    org_id = _normalize_text(organization_id)
    if not org_id:
        raise ValueError("ORGANIZATION_REQUIRED")

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, slug, name, status, tenant_status, provisioning_error, schema_version, created_at, updated_at
                FROM organizations
                WHERE id = %s
                """,
                (org_id,),
            )
            org_row = cur.fetchone()
            if not org_row:
                raise ValueError("ORGANIZATION_NOT_FOUND")

        organization = {
            "id": _normalize_text(org_row[0]),
            "slug": _normalize_text(org_row[1]),
            "name": _normalize_text(org_row[2]),
            "status": _normalize_text(org_row[3]),
            "created_at": str(org_row[7]) if org_row[7] is not None else None,
            "updated_at": str(org_row[8]) if org_row[8] is not None else None,
        }
        tenant_status = _normalize_text(org_row[4]) or organization["status"]
        provisioning_error = _normalize_text(org_row[5]) or None
        return {
            "organization": organization,
            "tenant_registry": {
                "organization_id": organization["id"],
                "status": tenant_status,
                "schema_version": _normalize_text(org_row[6]) or None,
            },
            "latest_job": {
                "organization_id": organization["id"],
                "status": tenant_status,
                "error": provisioning_error,
            } if provisioning_error or tenant_status not in {"", "active"} else None,
        }

    return _with_pg_retry(_run)


def list_organizations_overview(organization_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if not ensure_control_plane_foundation():
        raise ValueError("CONTROL_PLANE_UNAVAILABLE")
    normalized_ids = [value for value in (_normalize_text(item) for item in (organization_ids or [])) if value]

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            query = """
                SELECT
                  o.id,
                  o.slug,
                  o.name,
                  o.status,
                  o.tenant_status AS tenant_status,
                  COALESCE(mem.member_count, 0) AS member_count,
                  COALESCE(inv.pending_invite_count, 0) AS pending_invite_count
                FROM organizations o
                LEFT JOIN (
                  SELECT organization_id, COUNT(*) AS member_count
                  FROM organization_members
                  WHERE status = 'active'
                  GROUP BY organization_id
                ) mem ON mem.organization_id = o.id
                LEFT JOIN (
                  SELECT organization_id, COUNT(*) AS pending_invite_count
                  FROM organization_invites
                  WHERE status = 'pending'
                  GROUP BY organization_id
                ) inv ON inv.organization_id = o.id
                WHERE o.status <> 'deleted'
            """
            params: List[Any] = []
            if normalized_ids:
                query += " AND o.id = ANY(%s)"
                params.append(normalized_ids)
            query += " ORDER BY lower(o.name), o.id"
            cur.execute(query, params)
            rows = _extract_rows(cur)
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    **_org_public(row),
                    "tenant_status": _normalize_text(row.get("tenant_status")) or None,
                    "member_count": int(row.get("member_count") or 0),
                    "pending_invite_count": int(row.get("pending_invite_count") or 0),
                }
            )
        return out

    return _with_pg_retry(_run)


def list_organization_members(organization_id: str) -> List[Dict[str, Any]]:
    if not ensure_control_plane_foundation():
        raise ValueError("CONTROL_PLANE_UNAVAILABLE")
    org_id = _normalize_text(organization_id)
    if not org_id:
        raise ValueError("ORGANIZATION_REQUIRED")

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  om.id,
                  om.organization_id,
                  om.user_id,
                  om.org_role_code,
                  om.status,
                  om.created_at,
                  om.updated_at,
                  pu.email,
                  pu.name,
                  pu.status AS user_status,
                  pu.last_login_at
                FROM organization_members om
                JOIN users pu ON pu.id = om.user_id
                WHERE om.organization_id = %s
                ORDER BY
                  CASE om.org_role_code
                    WHEN 'org_owner' THEN 1
                    WHEN 'org_admin' THEN 2
                    WHEN 'org_editor' THEN 3
                    ELSE 4
                  END,
                  lower(pu.name),
                  lower(pu.email)
                """,
                (org_id,),
            )
            rows = _extract_rows(cur)
        return [
            {
                "id": _normalize_text(row.get("id")),
                "organization_id": _normalize_text(row.get("organization_id")),
                "user_id": _normalize_text(row.get("user_id")),
                "org_role_code": _normalize_text(row.get("org_role_code")),
                "status": _normalize_text(row.get("status")) or "active",
                "created_at": str(row.get("created_at")) if row.get("created_at") is not None else None,
                "updated_at": str(row.get("updated_at")) if row.get("updated_at") is not None else None,
                "email": _normalize_text(row.get("email")),
                "name": _normalize_text(row.get("name")),
                "user_status": _normalize_text(row.get("user_status")) or "active",
                "last_login_at": str(row.get("last_login_at")) if row.get("last_login_at") is not None else None,
            }
            for row in rows
        ]

    return _with_pg_retry(_run)


def list_organization_invites(organization_id: str) -> List[Dict[str, Any]]:
    if not ensure_control_plane_foundation():
        raise ValueError("CONTROL_PLANE_UNAVAILABLE")
    org_id = _normalize_text(organization_id)
    if not org_id:
        raise ValueError("ORGANIZATION_REQUIRED")

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  oi.id,
                  oi.organization_id,
                  oi.email,
                  oi.org_role_code,
                  oi.status,
                  oi.expires_at,
                  oi.accepted_at,
                  oi.created_at,
                  creator.name AS created_by_name,
                  creator.email AS created_by_email
                FROM organization_invites oi
                LEFT JOIN users creator ON creator.id = oi.created_by_user_id
                WHERE oi.organization_id = %s
                ORDER BY
                  CASE oi.status WHEN 'pending' THEN 1 ELSE 2 END,
                  oi.created_at DESC,
                  oi.id DESC
                """,
                (org_id,),
            )
            rows = _extract_rows(cur)
        return [
            {
                "id": _normalize_text(row.get("id")),
                "organization_id": _normalize_text(row.get("organization_id")),
                "email": _normalize_text(row.get("email")),
                "org_role_code": _normalize_text(row.get("org_role_code")),
                "status": _normalize_text(row.get("status")) or "pending",
                "expires_at": str(row.get("expires_at")) if row.get("expires_at") is not None else None,
                "accepted_at": str(row.get("accepted_at")) if row.get("accepted_at") is not None else None,
                "created_at": str(row.get("created_at")) if row.get("created_at") is not None else None,
                "created_by_name": _normalize_text(row.get("created_by_name")) or None,
                "created_by_email": _normalize_text(row.get("created_by_email")) or None,
            }
            for row in rows
        ]

    return _with_pg_retry(_run)
