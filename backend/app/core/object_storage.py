from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ObjectStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectMeta:
    key: str
    content_type: str
    size: int


@dataclass(frozen=True)
class ObjectPayload:
    key: str
    content_type: str
    size: int
    data: bytes


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def s3_enabled() -> bool:
    return _env("S3_ENABLED", "0").lower() in {"1", "true", "yes", "on"}


def _require(name: str) -> str:
    value = _env(name)
    if not value:
        raise ObjectStorageError(f"S3_CONFIG_MISSING:{name}")
    return value


def _load_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
        from botocore.exceptions import ClientError  # type: ignore
        return boto3, Config, ClientError
    except Exception as exc:
        raise ObjectStorageError("S3_DRIVER_MISSING:boto3") from exc


def _client():
    boto3, Config, _ = _load_boto3()
    endpoint = _require("S3_ENDPOINT")
    region = _env("S3_REGION", "ru-1")
    access_key = _require("S3_ACCESS_KEY_ID")
    secret_key = _require("S3_SECRET_ACCESS_KEY")
    force_path_style = _env("S3_FORCE_PATH_STYLE", "1").lower() in {"1", "true", "yes", "on"}
    signature_version = _env("S3_SIGNATURE_VERSION", "s3v4")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version=signature_version, s3={"addressing_style": "path" if force_path_style else "virtual"}),
    )


def _bucket() -> str:
    return _require("S3_BUCKET")


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> ObjectMeta:
    client = _client()
    client.put_object(Bucket=_bucket(), Key=key, Body=io.BytesIO(data), ContentType=content_type)
    return ObjectMeta(key=key, content_type=content_type, size=len(data))


def delete_object(key: str) -> None:
    _, _, ClientError = _load_boto3()
    client = _client()
    try:
        client.delete_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code") or "")
        if code in {"NoSuchKey", "404"}:
            raise FileNotFoundError(key) from exc
        raise ObjectStorageError(f"S3_DELETE_FAILED:{code or 'unknown'}") from exc


def get_object(key: str) -> ObjectPayload:
    _, _, ClientError = _load_boto3()
    client = _client()
    try:
        response = client.get_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code") or "")
        if code in {"NoSuchKey", "404"}:
            raise FileNotFoundError(key) from exc
        raise ObjectStorageError(f"S3_GET_FAILED:{code or 'unknown'}") from exc
    body = response["Body"].read()
    return ObjectPayload(
        key=key,
        content_type=str(response.get("ContentType") or "application/octet-stream"),
        size=int(response.get("ContentLength") or len(body)),
        data=body,
    )


def head_object(key: str) -> Optional[ObjectMeta]:
    _, _, ClientError = _load_boto3()
    client = _client()
    try:
        response = client.head_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code") or "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise ObjectStorageError(f"S3_HEAD_FAILED:{code or 'unknown'}") from exc
    return ObjectMeta(
        key=key,
        content_type=str(response.get("ContentType") or "application/octet-stream"),
        size=int(response.get("ContentLength") or 0),
    )

