"""
Cloudflare R2 object storage service wrapper.

Provides upload, delete, and presigned URL generation for temporary
video storage during the content posting pipeline.
"""

import uuid
from datetime import datetime
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from django.conf import settings

from utils.custom_logger import CustomLogger


class R2StorageService:
    """
    Thin wrapper around boto3 S3 client pointed at Cloudflare R2.

    All methods are staticmethods — no instance state needed.
    """

    _client = None

    @classmethod
    def _get_client(cls):
        """Lazy-initialise and cache the boto3 S3 client configured for R2."""
        if cls._client is None:
            cls._client = boto3.client(
                "s3",
                endpoint_url=settings.CLOUDFLARE_R2_ENDPOINT,
                aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY,
                aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET,
                config=BotoConfig(
                    region_name="auto",
                    signature_version="s3v4",
                ),
            )
        return cls._client

    @classmethod
    def generate_key(cls, prefix: str = "videos", extension: str = "mp4") -> str:
        """
        Generate a unique R2 object key.

        Format: {prefix}/{date}/{uuid}.{extension}
        """
        date_str = datetime.now(datetime.timezone.utc)().strftime("%Y-%m-%d")
        unique_id = uuid.uuid4().hex
        return f"{prefix}/{date_str}/{unique_id}.{extension}"

    @classmethod
    def upload_file(
        cls,
        file_bytes: bytes,
        key: str,
        content_type: str = "video/mp4",
    ) -> None:
        """
        Upload raw bytes to the R2 bucket.

        Raises Exception on failure (logged internally).
        """
        client = cls._get_client()
        try:
            client.put_object(
                Bucket=settings.CLOUDFLARE_R2_BUCKET,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
            CustomLogger.info(
                "R2 upload succeeded",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
        except Exception:
            CustomLogger.exception(
                "R2 upload failed",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            raise

    @classmethod
    def delete_file(cls, key: str) -> bool:
        """
        Delete an object from the R2 bucket.

        Returns True on success; logs and returns False on failure.
        """
        client = cls._get_client()
        try:
            client.delete_object(
                Bucket=settings.CLOUDFLARE_R2_BUCKET,
                Key=key,
            )
            CustomLogger.info(
                "R2 delete succeeded",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            return True
        except Exception:
            CustomLogger.exception(
                "R2 delete failed",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            return False

    @classmethod
    def generate_presigned_url(cls, key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for temporary public access to an R2 object.

        :param key: Object key in the bucket.
        :param expiration: URL lifetime in seconds (default 1 hour).
        :return: Presigned URL string, or None on failure.
        """
        client = cls._get_client()
        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.CLOUDFLARE_R2_BUCKET,
                    "Key": key,
                },
                ExpiresIn=expiration,
            )
            return url
        except Exception:
            CustomLogger.exception(
                "R2 presigned URL generation failed",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            return None