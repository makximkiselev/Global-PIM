from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import fcntl

_PG_STATE = threading.local()
_PG_TABLE_READY = False
_DOC_CACHE_TTL_SECONDS = 15.0
_DOC_CACHE: dict[str, tuple[float, Any]] = {}

DATA_DIR = Path(__file__).resolve().parents[2] / "data"  # backend/data
SQLITE_PATH = DATA_DIR / "pim.db"


class JsonStoreError(RuntimeError):
    pass


@dataclass
class FileLock:
    path: Path | None = None
    stale_seconds: int = 30
    _fh: Any = None

    def acquire(self, timeout: float = 5.0, poll: float = 0.05, blocking: bool = True) -> bool:
        if self.path is None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._fh is None or getattr(self._fh, "closed", True):
            self._fh = open(self.path, "a+", encoding="utf-8")
        deadline = time.time() + max(timeout, 0.0)
        while True:
            try:
                flags = fcntl.LOCK_EX
                if not blocking:
                    flags |= fcntl.LOCK_NB
                fcntl.flock(self._fh.fileno(), flags)
                self._fh.seek(0)
                self._fh.truncate()
                self._fh.write(str(os.getpid()))
                self._fh.flush()
                return True
            except BlockingIOError:
                if not blocking or time.time() >= deadline:
                    return False
                time.sleep(max(poll, 0.01))

    def release(self) -> None:
        if self._fh is None or getattr(self._fh, "closed", True):
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None


def _env_path() -> Path:
    return DATA_DIR.parent / ".env"


def _env_file_value(key: str) -> str:
    env_path = _env_path()
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() != key:
                continue
            val = v.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            return val.strip()
    except Exception:
        return ""
    return ""


def _database_url() -> str:
    return (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("PIM_DATABASE_URL", "").strip()
        or _env_file_value("DATABASE_URL")
        or _env_file_value("PIM_DATABASE_URL")
    )


def _storage_backend() -> str:
    explicit = (
        os.getenv("PIM_STORAGE_BACKEND", "").strip().lower()
        or _env_file_value("PIM_STORAGE_BACKEND").lower()
    )
    if explicit == "postgres":
        return explicit
    if explicit == "sqlite":
        return explicit
    dsn = _database_url()
    if dsn.startswith("postgres://") or dsn.startswith("postgresql://"):
        return "postgres"
    return "postgres"


def _assert_postgres_runtime() -> None:
    backend = _storage_backend()
    if backend != "postgres":
        raise JsonStoreError(
            f"POSTGRES_REQUIRED: runtime backend '{backend}' is not supported. Configure PIM_STORAGE_BACKEND=postgres and DATABASE_URL."
        )
    if not _database_url():
        raise JsonStoreError("DATABASE_URL_MISSING")


def _load_psycopg():
    try:
        import psycopg  # type: ignore
        return psycopg, "psycopg"
    except Exception:
        pass
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json  # type: ignore
        return (psycopg2, Json), "psycopg2"
    except Exception:
        pass
    raise JsonStoreError("POSTGRES_DRIVER_MISSING: install psycopg[binary] or psycopg2-binary")


def _db_connect_sqlite() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SQLITE_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _pg_connect():
    dsn = _database_url()
    if not dsn:
        raise JsonStoreError("DATABASE_URL_MISSING")
    conn = getattr(_PG_STATE, "conn", None)
    kind = getattr(_PG_STATE, "kind", "")
    adapter = getattr(_PG_STATE, "json_adapter", None)
    if conn is not None:
        try:
            if kind == "psycopg":
                if not getattr(conn, "closed", True):
                    return conn, kind, adapter
            elif kind == "psycopg2":
                if getattr(conn, "closed", 1) == 0:
                    return conn, kind, adapter
        except Exception:
            _PG_STATE.conn = None
            _PG_STATE.kind = ""
            _PG_STATE.json_adapter = None
    driver, kind = _load_psycopg()
    if kind == "psycopg":
        conn = driver.connect(dsn, autocommit=True)
        _PG_STATE.conn = conn
        _PG_STATE.kind = kind
        _PG_STATE.json_adapter = None
        return conn, kind, None
    psycopg2_mod, Json = driver
    conn = psycopg2_mod.connect(dsn)
    conn.autocommit = True
    _PG_STATE.conn = conn
    _PG_STATE.kind = kind
    _PG_STATE.json_adapter = Json
    return conn, kind, Json


def _reset_pg_connection() -> None:
    global _PG_TABLE_READY
    conn = getattr(_PG_STATE, "conn", None)
    _PG_STATE.conn = None
    _PG_STATE.kind = ""
    _PG_STATE.json_adapter = None
    _PG_TABLE_READY = False
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


def _is_retryable_pg_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "idle-session timeout",
        "terminating connection",
        "server closed the connection unexpectedly",
        "connection already closed",
        "broken pipe",
        "ssl connection has been closed unexpectedly",
    )
    return any(marker in message for marker in markers)


def _ensure_pg_table(conn: Any) -> None:
    global _PG_TABLE_READY
    if _PG_TABLE_READY:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS json_documents (
              path TEXT PRIMARY KEY,
              payload JSONB NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    _PG_TABLE_READY = True


def _is_under_data_dir(path: Path) -> bool:
    try:
        path.resolve().relative_to(DATA_DIR.resolve())
        return True
    except Exception:
        return False


def _table_name_for_path(path: Path) -> str:
    rel = path.resolve().relative_to(DATA_DIR.resolve())
    parts = [str(x) for x in rel.parts]
    joined = "__".join(parts)
    base = joined.replace(".", "_").replace("-", "_").replace(" ", "_").lower()
    safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in base).strip("_")
    if not safe:
        safe = "root"
    return f"doc_{safe}"


def _doc_key_for_path(path: Path) -> str:
    return str(path.resolve().relative_to(DATA_DIR.resolve())).replace("\\", "/")


def _cache_get(key: str) -> Any | None:
    entry = _DOC_CACHE.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if expires_at <= time.monotonic():
        _DOC_CACHE.pop(key, None)
        return None
    return deepcopy(payload)


def _cache_set(key: str, payload: Any) -> None:
    _DOC_CACHE[key] = (time.monotonic() + _DOC_CACHE_TTL_SECONDS, deepcopy(payload))


def _cache_invalidate(key: str) -> None:
    _DOC_CACHE.pop(key, None)


def _ensure_doc_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(
        f'''
        CREATE TABLE IF NOT EXISTS "{table}" (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          payload TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        '''
    )


def _load_legacy_file(path: Path, default: Optional[Any]) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return default if default is not None else {}


def migrate_legacy_json_files_to_sql(remove_after: bool = False) -> int:
    moved = 0
    if _storage_backend() == "postgres":
        conn, _, Json = _pg_connect()
        try:
            _ensure_pg_table(conn)
            with conn.cursor() as cur:
                for path in DATA_DIR.rglob("*.json"):
                    if ".locks" in path.parts:
                        continue
                    key = _doc_key_for_path(path)
                    cur.execute("SELECT 1 FROM json_documents WHERE path = %s", (key,))
                    if cur.fetchone():
                        continue
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if Json is not None:
                        cur.execute(
                            "INSERT INTO json_documents (path, payload, updated_at) VALUES (%s, %s, NOW()) ON CONFLICT (path) DO NOTHING",
                            (key, Json(payload)),
                        )
                    else:
                        cur.execute(
                            "INSERT INTO json_documents (path, payload, updated_at) VALUES (%s, %s::jsonb, NOW()) ON CONFLICT (path) DO NOTHING",
                            (key, json.dumps(payload, ensure_ascii=False)),
                        )
                    moved += 1
                    if remove_after:
                        path.unlink(missing_ok=True)
            return moved
        finally:
            conn.close()

    with _db_connect_sqlite() as conn:
        for path in DATA_DIR.rglob("*.json"):
            if ".locks" in path.parts:
                continue
            table = _table_name_for_path(path)
            _ensure_doc_table(conn, table)
            cur = conn.execute(f'SELECT payload FROM "{table}" WHERE id=1')
            row = cur.fetchone()
            if row:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            conn.execute(
                f'INSERT OR REPLACE INTO "{table}" (id, payload, updated_at) VALUES (1, ?, datetime("now"))',
                (json.dumps(payload, ensure_ascii=False),),
            )
            moved += 1
            if remove_after:
                path.unlink(missing_ok=True)
        conn.commit()
    return moved


def migrate_sqlite_docs_to_postgres(remove_after: bool = False) -> int:
    if _storage_backend() != "postgres":
        return 0
    if not SQLITE_PATH.exists():
        return 0
    conn_pg, _, Json = _pg_connect()
    moved = 0
    try:
        _ensure_pg_table(conn_pg)
        with sqlite3.connect(str(SQLITE_PATH)) as conn_sqlite:
            conn_sqlite.row_factory = sqlite3.Row
            rows = conn_sqlite.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'doc_%'"
            ).fetchall()
            with conn_pg.cursor() as cur_pg:
                for row in rows:
                    table = row[0] if not isinstance(row, sqlite3.Row) else row["name"]
                    cur = conn_sqlite.execute(f'SELECT payload FROM "{table}" WHERE id=1')
                    doc_row = cur.fetchone()
                    if not doc_row:
                        continue
                    raw = doc_row[0] if not isinstance(doc_row, sqlite3.Row) else doc_row["payload"]
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    rel_key = table.removeprefix("doc_").replace("__", "/")
                    rel_key = rel_key.replace("_json", ".json")
                    if Json is not None:
                        cur_pg.execute(
                            "INSERT INTO json_documents (path, payload, updated_at) VALUES (%s, %s, NOW()) ON CONFLICT (path) DO NOTHING",
                            (rel_key, Json(payload)),
                        )
                    else:
                        cur_pg.execute(
                            "INSERT INTO json_documents (path, payload, updated_at) VALUES (%s, %s::jsonb, NOW()) ON CONFLICT (path) DO NOTHING",
                            (rel_key, json.dumps(payload, ensure_ascii=False)),
                        )
                    moved += 1
        if remove_after:
            SQLITE_PATH.unlink(missing_ok=True)
        return moved
    finally:
        conn_pg.close()


def read_doc(path: Path, default: Optional[Any] = None) -> Any:
    p = Path(path)
    if not _is_under_data_dir(p):
        raise JsonStoreError(f"SQL_ONLY_MODE_PATH_NOT_ALLOWED: {p}")

    _assert_postgres_runtime()
    key = _doc_key_for_path(p)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    for attempt in range(2):
        try:
            conn, _, _ = _pg_connect()
            _ensure_pg_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM json_documents WHERE path = %s", (key,))
                row = cur.fetchone()
                if not row:
                    return default if default is not None else {}
                raw = row[0]
                if isinstance(raw, (dict, list)):
                    return raw
                if raw is None:
                    return default if default is not None else {}
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    return default if default is not None else {}
                _cache_set(key, payload)
                return deepcopy(payload)
        except Exception as exc:
            if attempt == 0 and _is_retryable_pg_error(exc):
                _reset_pg_connection()
                continue
            raise


def write_doc(path: Path, data: Any) -> None:
    p = Path(path)
    if not _is_under_data_dir(p):
        raise JsonStoreError(f"SQL_ONLY_MODE_PATH_NOT_ALLOWED: {p}")

    _assert_postgres_runtime()
    key = _doc_key_for_path(p)
    _cache_invalidate(key)
    for attempt in range(2):
        try:
            conn, _, Json = _pg_connect()
            _ensure_pg_table(conn)
            with conn.cursor() as cur:
                if Json is not None:
                    cur.execute(
                        """
                        INSERT INTO json_documents (path, payload, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (path)
                        DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                        """,
                        (key, Json(data)),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO json_documents (path, payload, updated_at)
                        VALUES (%s, %s::jsonb, NOW())
                        ON CONFLICT (path)
                        DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                        """,
                        (key, json.dumps(data, ensure_ascii=False)),
                    )
            break
        except Exception as exc:
            if attempt == 0 and _is_retryable_pg_error(exc):
                _reset_pg_connection()
                continue
            raise
    _cache_set(key, data)


def with_lock(filename: str) -> FileLock:
    safe = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "_" for ch in str(filename or "").strip()).strip("_")
    if not safe:
        safe = "lock"
    lock_dir = DATA_DIR / ".locks"
    return FileLock(lock_dir / f"{safe}.lock")


read_json = read_doc
write_json = write_doc
