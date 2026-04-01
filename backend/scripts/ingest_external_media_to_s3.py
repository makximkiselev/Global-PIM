from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.core.json_store import DATA_DIR, read_doc, write_doc
from app.core.object_storage import head_object, s3_enabled, upload_bytes


PRODUCTS_PATH = DATA_DIR / "products.json"
INTERNAL_HOSTS = {"pim.id-smart.ru", "www.pim.id-smart.ru"}
MEDIA_FIELDS = ("media_images", "media_videos", "media_cover")
DOCUMENT_FIELDS = ("documents",)


def _is_external_url(url: str) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    if raw.startswith("/api/uploads/"):
        return False
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.netloc or "").lower()
    if host in INTERNAL_HOSTS:
        return False
    return True


def _sanitize_host(url: str) -> str:
    host = (urlparse(url).hostname or "external").lower()
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in host)


def _ext_from_url_or_type(url: str, content_type: str) -> str:
    path = urlparse(url).path or ""
    suffix = Path(path).suffix.lower()
    if suffix and len(suffix) <= 10:
        return suffix
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed:
        return guessed
    return ".bin"


def _make_storage_key(product_id: str, kind: str, source_url: str, content_type: str) -> str:
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:16]
    host = _sanitize_host(source_url)
    ext = _ext_from_url_or_type(source_url, content_type)
    return f"ingested/{host}/{product_id}/{kind}_{digest}{ext}"


def _download(url: str) -> tuple[bytes, str]:
    req = Request(
        url,
        headers={
            "User-Agent": "GlobalPIM/1.0 (+https://pim.id-smart.ru)",
            "Accept": "*/*",
        },
    )
    with urlopen(req, timeout=45) as response:
        data = response.read()
        content_type = response.info().get_content_type() or "application/octet-stream"
        return data, content_type


def _rewrite_media_item(product_id: str, field_name: str, item: dict[str, Any], stats: dict[str, int]) -> None:
    source_url = str(item.get("url") or "").strip()
    if not _is_external_url(source_url):
        return

    stats["external_found"] += 1
    try:
        payload, content_type = _download(source_url)
        key = _make_storage_key(product_id, field_name, source_url, content_type)
        if head_object(key) is None:
            upload_bytes(key, payload, content_type)
            stats["uploaded"] += 1
        else:
            stats["skipped_existing"] += 1
        item["url"] = f"/api/uploads/{key}"
        item["source_url"] = source_url
        item["storage"] = "s3"
        item["source_type"] = "external_import"
        item["source_host"] = _sanitize_host(source_url)
        stats["rewritten"] += 1
    except Exception as exc:
        item["ingest_error"] = str(exc)
        stats["errors"] += 1


def main() -> None:
    if not s3_enabled():
        raise SystemExit("S3_NOT_CONFIGURED")

    doc = read_doc(PRODUCTS_PATH, default={"items": []})
    items = doc.get("items") if isinstance(doc, dict) else []
    if not isinstance(items, list):
        raise SystemExit("PRODUCTS_INVALID")

    stats = {
        "products": 0,
        "external_found": 0,
        "rewritten": 0,
        "uploaded": 0,
        "skipped_existing": 0,
        "errors": 0,
    }
    flush_every = 25
    pending_writes = 0

    for product in items:
        if not isinstance(product, dict):
            continue
        stats["products"] += 1
        product_id = str(product.get("id") or "").strip() or "unknown"
        content = product.get("content") if isinstance(product.get("content"), dict) else None
        if not isinstance(content, dict):
            continue
        for field in MEDIA_FIELDS:
            values = content.get(field)
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict):
                    before = stats["rewritten"]
                    _rewrite_media_item(product_id, field, item, stats)
                    if stats["rewritten"] > before:
                        pending_writes += 1
                        if pending_writes >= flush_every:
                            write_doc(PRODUCTS_PATH, {"items": items})
                            print(
                                f"checkpoint rewritten={stats['rewritten']} uploaded={stats['uploaded']} "
                                f"skipped_existing={stats['skipped_existing']} errors={stats['errors']}"
                            )
                            pending_writes = 0
        for field in DOCUMENT_FIELDS:
            values = content.get(field)
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict):
                    before = stats["rewritten"]
                    _rewrite_media_item(product_id, field, item, stats)
                    if stats["rewritten"] > before:
                        pending_writes += 1
                        if pending_writes >= flush_every:
                            write_doc(PRODUCTS_PATH, {"items": items})
                            print(
                                f"checkpoint rewritten={stats['rewritten']} uploaded={stats['uploaded']} "
                                f"skipped_existing={stats['skipped_existing']} errors={stats['errors']}"
                            )
                            pending_writes = 0

    write_doc(PRODUCTS_PATH, {"items": items})
    print(
        " ".join(
            [
                f"products={stats['products']}",
                f"external_found={stats['external_found']}",
                f"rewritten={stats['rewritten']}",
                f"uploaded={stats['uploaded']}",
                f"skipped_existing={stats['skipped_existing']}",
                f"errors={stats['errors']}",
            ]
        )
    )


if __name__ == "__main__":
    main()
