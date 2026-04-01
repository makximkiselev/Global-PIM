from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.object_storage import ObjectStorageError, get_object, s3_enabled

router = APIRouter()


@router.get("/uploads/{storage_path:path}")
def get_upload(storage_path: str):
    relative = unquote(str(storage_path or "").lstrip("/"))
    if not relative:
        raise HTTPException(status_code=404, detail="UPLOAD_NOT_FOUND")
    if not s3_enabled():
        raise HTTPException(status_code=503, detail="S3_NOT_CONFIGURED")

    try:
        payload = get_object(relative)
        filename = PurePosixPath(relative).name or "file"
        media_type = payload.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        headers = {
            "Content-Length": str(payload.size),
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=31536000, immutable",
        }
        return Response(content=payload.data, media_type=media_type, headers=headers)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="UPLOAD_NOT_FOUND")
    except ObjectStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
