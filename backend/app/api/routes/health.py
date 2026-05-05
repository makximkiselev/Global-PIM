from fastapi import APIRouter

from app.core.object_storage import ObjectStorageError, s3_enabled

router = APIRouter()

@router.get("/health")
def health():
    return {"ok": True}


@router.get("/health/storage")
def storage_health():
    try:
        enabled = s3_enabled()
    except ObjectStorageError as exc:
        return {"ok": False, "s3_enabled": False, "error": str(exc)}
    return {"ok": bool(enabled), "s3_enabled": bool(enabled)}
