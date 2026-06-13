#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

ENV_PATH = BACKEND_DIR / ".env"
MEDIA_FIELDS = ("media", "media_images", "media_videos", "media_cover")
MEDIA_SOURCE_FIELDS = ("media", "media_images", "media_videos", "media_cover")
S3_MEDIA_PREFIXES = ("media/", "media_images/", "media_videos/", "media_cover/")


def _load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in os.environ:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


_load_env_file()

from app.core.object_storage import ObjectStorageError, delete_object, s3_enabled  # noqa: E402
from app.storage.relational_pim_store import _pg_connect  # noqa: E402


def _upload_key_from_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = unquote(parsed.path or raw)
    prefix = "/api/uploads/"
    if not path.startswith(prefix):
        return ""
    key = path[len(prefix):].lstrip("/")
    if not key.startswith(S3_MEDIA_PREFIXES):
        return ""
    return key


def _collect_media_keys(content: Any) -> set[str]:
    if not isinstance(content, dict):
        return set()
    keys: set[str] = set()
    for field in MEDIA_FIELDS:
        values = content.get(field)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                key = _upload_key_from_url(item.get("url"))
            else:
                key = _upload_key_from_url(item)
            if key:
                keys.add(key)
    return keys


def _cleared_content(content: Any) -> dict[str, Any]:
    next_content = dict(content) if isinstance(content, dict) else {}
    for field in MEDIA_FIELDS:
        next_content[field] = []
    source_values = next_content.get("source_values")
    if isinstance(source_values, dict):
        for field in MEDIA_SOURCE_FIELDS:
            source_values.pop(field, None)
        next_content["source_values"] = source_values
    return next_content


def _json_param(value: dict[str, Any]) -> Any:
    try:
        import psycopg  # type: ignore

        return json.dumps(value, ensure_ascii=False) if psycopg else json.dumps(value, ensure_ascii=False)
    except Exception:
        return json.dumps(value, ensure_ascii=False)


def _fetch_rows(table: str) -> list[tuple[str, str, dict[str, Any]]]:
    conn, _, _ = _pg_connect()
    with conn.cursor() as cur:
        if table == "products_rel":
            cur.execute("SELECT organization_id, id, content_json FROM products_rel ORDER BY organization_id, id")
        elif table == "product_variants_rel":
            cur.execute("SELECT '' AS organization_id, id, content_json FROM product_variants_rel ORDER BY id")
        else:
            raise ValueError(table)
        rows = cur.fetchall() or []
    out: list[tuple[str, str, dict[str, Any]]] = []
    for org_id, row_id, content in rows:
        out.append((str(org_id or ""), str(row_id or ""), content if isinstance(content, dict) else {}))
    return out


def _update_rows(table: str, rows: list[tuple[str, str, dict[str, Any]]]) -> None:
    if not rows:
        return
    conn, _, _ = _pg_connect()
    with conn.cursor() as cur:
        for org_id, row_id, content in rows:
            if table == "products_rel":
                cur.execute(
                    "UPDATE products_rel SET content_json = %s::jsonb WHERE organization_id = %s AND id = %s",
                    (_json_param(content), org_id, row_id),
                )
            elif table == "product_variants_rel":
                cur.execute(
                    "UPDATE product_variants_rel SET content_json = %s::jsonb WHERE id = %s",
                    (_json_param(content), row_id),
                )
    try:
        conn.commit()
    except Exception:
        pass


def _list_s3_media_keys() -> set[str]:
    from app.core.object_storage import _bucket, _client  # type: ignore

    client = _client()
    bucket = _bucket()
    keys: set[str] = set()
    for prefix in S3_MEDIA_PREFIXES:
        continuation: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                key = str(item.get("Key") or "").strip()
                if key:
                    keys.add(key)
            if not response.get("IsTruncated"):
                break
            continuation = str(response.get("NextContinuationToken") or "")
            if not continuation:
                break
    return keys


def _delete_s3_keys(keys: set[str], *, apply: bool) -> tuple[int, int]:
    deleted = 0
    errors = 0
    if not apply:
        return deleted, errors
    for key in sorted(keys):
        try:
            delete_object(key)
            deleted += 1
        except FileNotFoundError:
            deleted += 1
        except ObjectStorageError as exc:
            errors += 1
            print(f"s3_delete_error key={key} error={exc}", file=sys.stderr)
    return deleted, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear product media fields and delete PIM media objects from S3.")
    parser.add_argument("--apply", action="store_true", help="Write DB changes and delete S3 objects. Default is dry-run.")
    parser.add_argument(
        "--delete-s3-prefixes",
        action="store_true",
        help="Delete every object under media/, media_images/, media_videos/, media_cover/, not only keys referenced by products.",
    )
    args = parser.parse_args()

    if not s3_enabled():
        raise SystemExit("S3_NOT_CONFIGURED")

    referenced_keys: set[str] = set()
    changed_by_table: dict[str, list[tuple[str, str, dict[str, Any]]]] = {"products_rel": [], "product_variants_rel": []}
    scanned = 0
    for table in ("products_rel", "product_variants_rel"):
        for _org_id, row_id, content in _fetch_rows(table):
            scanned += 1
            keys = _collect_media_keys(content)
            referenced_keys.update(keys)
            has_media_values = any(isinstance(content.get(field), list) and content.get(field) for field in MEDIA_FIELDS)
            has_media_sources = isinstance(content.get("source_values"), dict) and any(
                field in content.get("source_values", {}) for field in MEDIA_SOURCE_FIELDS
            )
            if has_media_values or has_media_sources:
                changed_by_table[table].append((_org_id, row_id, _cleared_content(content)))

    s3_keys = _list_s3_media_keys() if args.delete_s3_prefixes else set()
    keys_to_delete = referenced_keys | s3_keys

    print(
        " ".join(
            [
                f"apply={args.apply}",
                f"scanned_rows={scanned}",
                f"changed_products={len(changed_by_table['products_rel'])}",
                f"changed_variants={len(changed_by_table['product_variants_rel'])}",
                f"referenced_s3_keys={len(referenced_keys)}",
                f"prefix_s3_keys={len(s3_keys)}",
                f"delete_s3_keys={len(keys_to_delete)}",
            ]
        )
    )

    if args.apply:
        for table, rows in changed_by_table.items():
            _update_rows(table, rows)
    deleted, errors = _delete_s3_keys(keys_to_delete, apply=args.apply)
    print(f"s3_deleted={deleted} s3_errors={errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
