"""File storage — Cloudflare R2 with local fallback."""

import os
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

settings = get_settings()


def _r2_configured() -> bool:
    return bool(
        settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket_name
        and settings.r2_endpoint_url
    )


def save_upload(file_bytes: bytes, original_filename: str) -> str:
    """Persist an uploaded file and return its storage path or object key."""
    file_ext = Path(original_filename).suffix or ".pdf"
    object_key = f"requirements/{uuid.uuid4()}{file_ext}"

    if _r2_configured():
        client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
        )
        try:
            client.put_object(
                Bucket=settings.r2_bucket_name,
                Key=object_key,
                Body=file_bytes,
                ContentType="application/pdf",
            )
            return f"r2://{settings.r2_bucket_name}/{object_key}"
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"R2 upload failed: {exc}") from exc

    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    local_path = os.path.join(upload_dir, f"{uuid.uuid4()}{file_ext}")
    with open(local_path, "wb") as output_file:
        output_file.write(file_bytes)
    return local_path


def get_local_path(storage_path: str) -> str:
    """Return a local filesystem path for reading a stored file."""
    if storage_path.startswith("r2://"):
        if not _r2_configured():
            raise RuntimeError("R2 credentials required to read remote files")
        _, remainder = storage_path.split("r2://", 1)
        bucket, object_key = remainder.split("/", 1)
        client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
        )
        cache_dir = os.path.join(settings.upload_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        local_path = os.path.join(cache_dir, Path(object_key).name)
        client.download_file(bucket, object_key, local_path)
        return local_path
    return storage_path
