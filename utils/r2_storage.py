"""
Cloudflare R2 object storage service wrapper.

Provides upload, delete, download, and presigned URL generation for temporary
media storage (video and photo) during the content posting pipeline.
"""

import mimetypes
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from django.conf import settings

from utils.custom_logger import CustomLogger

# Mapping from our internal content type to R2 folder prefix and MIME type
CONTENT_TYPE_MAP = {
    "video": {"prefix": "videos", "mime": "video/mp4"},
    "photo": {"prefix": "photos", "mime": "image/jpeg"},
    "profile_picture": {"prefix": "profile_pictures", "mime": "image/jpeg"},
    "brand_logo": {"prefix": "brand_logos", "mime": "image/jpeg"},
    "platform_profile": {"prefix": "platform_profiles", "mime": "image/jpeg"},
}


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
    def generate_key(cls, content_type: str = "video", extension: str = None) -> str:
        """
        Generate a unique R2 object key based on content type.

        Format: {prefix}/{date}/{uuid}.{extension}

        :param content_type: "video" or "photo" — determines the folder prefix.
        :param extension: File extension (e.g. "mp4", "jpg"). If None, inferred
                          from content_type (mp4 for video, jpg for photo).
        """
        info = CONTENT_TYPE_MAP.get(content_type, CONTENT_TYPE_MAP["video"])
        ext = extension or ("mp4" if content_type == "video" else "jpg")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        unique_id = uuid.uuid4().hex
        return f"{info['prefix']}/{date_str}/{unique_id}.{ext}"

    @classmethod
    def upload_file(
        cls,
        file_bytes: bytes,
        key: str,
        content_type: str = "video",
    ) -> None:
        """
        Upload raw bytes to the R2 bucket.

        The MIME type is derived from the content_type parameter
        ("video" → video/mp4, "photo" → image/jpeg).

        :param file_bytes: Raw file data.
        :param key: R2 object key (generated via generate_key).
        :param content_type: "video" or "photo".
        Raises Exception on failure (logged internally).
        """
        info = CONTENT_TYPE_MAP.get(content_type, CONTENT_TYPE_MAP["video"])
        client = cls._get_client()
        try:
            client.put_object(
                Bucket=settings.CLOUDFLARE_R2_BUCKET,
                Key=key,
                Body=file_bytes,
                ContentType=info["mime"],
            )
            CustomLogger.info(
                "R2 upload succeeded",
                extra={
                    "bucket": settings.CLOUDFLARE_R2_BUCKET,
                    "key": key,
                    "content_type": content_type,
                    "mime": info["mime"],
                },
            )
        except Exception:
            CustomLogger.exception(
                "R2 upload failed",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            raise

    @classmethod
    def download_file(cls, key: str) -> bytes:
        """
        Download an object from the R2 bucket as raw bytes.

        :param key: Object key in the bucket.
        :return: Raw file bytes.
        Raises ValueError on failure.
        """
        client = cls._get_client()
        try:
            response = client.get_object(
                Bucket=settings.CLOUDFLARE_R2_BUCKET,
                Key=key,
            )
            return response["Body"].read()
        except Exception as e:
            CustomLogger.exception(
                "R2 download failed",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            raise ValueError(f"Failed to download media from R2: {str(e)}") from e

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
    def delete_from_url(cls, url: str) -> bool:
        """
        Extract the key from a public R2 URL and delete the object.
        Returns True if deleted or skipped (not our URL), False on failure.
        """
        if not url:
            return True

        public_domain = getattr(settings, "CLOUDFLARE_R2_PUBLIC_DOMAIN", None)
        if not public_domain:
            return True

        base_url = public_domain.rstrip("/")
        if url.startswith(f"{base_url}/"):
            key = url[len(f"{base_url}/") :]
            return cls.delete_file(key)

        return True

    @classmethod
    def generate_presigned_url(cls, key: str, expiration: int = 3600) -> str | None:
        """
        Generate a public URL for an R2 object.

         If CLOUDFLARE_R2_PUBLIC_DOMAIN is configured, it builds a clean,
         permanent public URL. Otherwise, it falls back to a signed S3 URL.

         :param key: Object key in the bucket.
         :param expiration: URL lifetime in seconds (default 1 hour).
         :return: Presigned URL string, or None on failure.
        """
        # 1. Use the custom domain if available (Perfect for TikTok photo pull)
        public_domain = getattr(settings, "CLOUDFLARE_R2_PUBLIC_DOMAIN", None)
        if public_domain:
            base_url = public_domain.rstrip("/")
            return f"{base_url}/{key}"

        # 2. Fallback to default boto3 presigned URL
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

    @classmethod
    def generate_presigned_upload_url(
        cls, content_type: str = "video", extension: str = None, expiration: int = 3600
    ) -> dict | None:
        """
        Generate a presigned URL for uploading a new object to R2.

        Returns a dict containing 'key' and 'url', or None on failure.
        """
        key = cls.generate_key(content_type, extension)
        info = CONTENT_TYPE_MAP.get(content_type, CONTENT_TYPE_MAP["video"])
        mime_type = info["mime"]
        if extension:
            guessed_mime = mimetypes.guess_type(f"file.{extension}")[0]
            if guessed_mime:
                mime_type = guessed_mime

        client = cls._get_client()

        try:
            url = client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.CLOUDFLARE_R2_BUCKET,
                    "Key": key,
                    "ContentType": mime_type,
                },
                ExpiresIn=expiration,
            )
            return {"key": key, "url": url}
        except Exception:
            CustomLogger.exception(
                "R2 presigned upload URL generation failed",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            return None

    @classmethod
    def is_file_accessible(cls, key: str) -> bool:
        """
        Check if a file is accessible via HEAD request to its public presigned URL.

        Useful for verifying that media uploaded via presigned URL is immediately
        available for social platform fetching.

        :param key: Object key in the bucket.
        :return: True if accessible (HTTP 200/206), False otherwise.
        """
        import requests

        try:
            url = cls.generate_presigned_url(key, expiration=3600)
            if not url:
                CustomLogger.warning(
                    "Failed to generate presigned URL for accessibility check",
                    extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
                )
                return False

            response = requests.head(url, timeout=10, allow_redirects=True)
            is_ready = response.status_code in (200, 206)

            if is_ready:
                CustomLogger.info(
                    "R2 file accessibility check passed",
                    extra={
                        "bucket": settings.CLOUDFLARE_R2_BUCKET,
                        "key": key,
                        "status_code": response.status_code,
                    },
                )
            else:
                CustomLogger.warning(
                    "R2 file not yet ready",
                    extra={
                        "bucket": settings.CLOUDFLARE_R2_BUCKET,
                        "key": key,
                        "status_code": response.status_code,
                    },
                )

            return is_ready
        except requests.RequestException as e:
            CustomLogger.warning(
                "R2 file accessibility check request failed",
                extra={
                    "bucket": settings.CLOUDFLARE_R2_BUCKET,
                    "key": key,
                    "error": str(e),
                },
            )
            return False
        except Exception as e:
            CustomLogger.exception(
                "R2 file accessibility check failed",
                extra={"bucket": settings.CLOUDFLARE_R2_BUCKET, "key": key},
            )
            return False
