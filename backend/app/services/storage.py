"""S3-compatible object storage.

Only the plain S3 API is used, never a vendor-specific SDK, so MinIO locally and
S3 or Cloudflare R2 in production differ by configuration alone.

Two clients exist on purpose:

* the internal client talks to storage over the container network and is used
  for server-side work such as HEAD, DELETE and listing;
* the public client exists only to sign URLs, because a presigned URL is signed
  against a specific host and the phone opening it cannot resolve a compose
  service name like ``minio``.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, NamedTuple

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


def _build_client(endpoint_url: str) -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


@lru_cache
def _internal_client() -> Any:
    return _build_client(get_settings().s3_endpoint_url)


@lru_cache
def _signing_client() -> Any:
    return _build_client(get_settings().s3_public_endpoint_url)


# ------------------------------------------------------------------ key layout
# Tenant-prefixed so deleting a film is a prefix sweep and lifecycle rules can
# archive originals independently of derivatives.


def original_key(film_id: str, shot_id: str) -> str:
    return f"films/{film_id}/originals/{shot_id}.jpg"


def derivative_key(film_id: str, shot_id: str, size: str) -> str:
    return f"films/{film_id}/derivatives/{size}/{shot_id}.webp"


def export_key(film_id: str, export_id: str) -> str:
    return f"films/{film_id}/exports/{export_id}.zip"


def film_prefix(film_id: str) -> str:
    return f"films/{film_id}/"


# --------------------------------------------------------------------- signing


async def presign_put(key: str, content_type: str = "image/jpeg") -> str:
    """URL the client PUTs raw bytes to. Photo data never passes through the API."""
    settings = get_settings()
    return await asyncio.to_thread(
        _signing_client().generate_presigned_url,
        ClientMethod="put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.upload_url_ttl_seconds,
    )


async def presign_get(key: str) -> str:
    """Short-lived read URL. Only ever minted after a film has developed."""
    settings = get_settings()
    return await asyncio.to_thread(
        _signing_client().generate_presigned_url,
        ClientMethod="get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.download_url_ttl_seconds,
    )


# ------------------------------------------------------------------- operations


class ObjectInfo(NamedTuple):
    size: int
    content_type: str


async def stat_object(key: str) -> ObjectInfo | None:
    """Size and declared type of a stored object, or None when it is absent.

    A presigned PUT names the key and content type but cannot bound the body,
    so this is how the API learns what a client actually uploaded.
    """
    settings = get_settings()

    def _head() -> ObjectInfo | None:
        try:
            response = _internal_client().head_object(Bucket=settings.s3_bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectInfo(
            size=int(response.get("ContentLength", 0)),
            content_type=str(response.get("ContentType", "")).lower(),
        )

    return await asyncio.to_thread(_head)


async def object_exists(key: str) -> bool:
    return await stat_object(key) is not None


async def delete_prefix(prefix: str) -> int:
    """Delete every object under a prefix. Used when a film is removed."""
    settings = get_settings()

    def _delete() -> int:
        client = _internal_client()
        paginator = client.get_paginator("list_objects_v2")
        removed = 0
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
            contents = page.get("Contents", [])
            if not contents:
                continue
            client.delete_objects(
                Bucket=settings.s3_bucket,
                Delete={"Objects": [{"Key": item["Key"]} for item in contents]},
            )
            removed += len(contents)
        return removed

    return await asyncio.to_thread(_delete)


async def delete_object(key: str) -> None:
    settings = get_settings()
    await asyncio.to_thread(
        _internal_client().delete_object, Bucket=settings.s3_bucket, Key=key
    )


# ------------------------------------------------------- synchronous (workers)
# Celery tasks are blocking, so they call boto3 directly instead of paying for
# a thread hop through the async wrappers above.


def download_bytes(key: str) -> bytes:
    settings = get_settings()
    response = _internal_client().get_object(Bucket=settings.s3_bucket, Key=key)
    return bytes(response["Body"].read())


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    _internal_client().put_object(
        Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
    )


def delete_object_sync(key: str) -> None:
    settings = get_settings()
    _internal_client().delete_object(Bucket=settings.s3_bucket, Key=key)


def object_exists_sync(key: str) -> bool:
    settings = get_settings()
    try:
        _internal_client().head_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    return True


async def bucket_ready() -> bool:
    settings = get_settings()

    def _head_bucket() -> bool:
        try:
            _internal_client().head_bucket(Bucket=settings.s3_bucket)
        except ClientError:
            return False
        return True

    return await asyncio.to_thread(_head_bucket)
