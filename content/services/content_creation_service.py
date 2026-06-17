"""
Service for creating ContentPost records from an incoming request,
including brand resolution, platform validation, R2 upload, and Celery dispatch.

Delegates cross-domain queries to BrandService and SocialAccountValidationService.
"""

from typing import List

from django.db import transaction

from content.models import ContentMedia, ContentPost, ContentPostPlatform
from content.tasks import publish_platform_entry
from users.services.brand_service import BrandService
from social_accounts.services.social_account_validation_service import SocialAccountValidationService
from utils.custom_logger import CustomLogger, log_exceptions
from utils.r2_storage import R2StorageService


class ContentCreationService:
    """
    Handles the full creation and publishing pipeline:
    validate inputs, resolve brand and platform connections, upload to R2,
    create DB records, and dispatch Celery tasks for each platform.
    """

    @classmethod
    @log_exceptions()
    def create_content_post(
        cls,
        *,
        user,
        media_files: list,
        text: str,
        platforms: List[str],
        content_type: str = "video",
    ) -> ContentPost:
        """
        Full creation + dispatch pipeline:
        1. Resolve the user's default brand (via BrandService)
        2. Validate every requested platform has a connected SocialAccount
        3. Upload each media file to R2 (videos go to videos/ folder, photos to photos/)
        4. Create ContentPost + ContentMedia + ContentPostPlatform entries
        5. Dispatch a Celery task for each platform entry

        :param media_files: List of Django UploadedFile objects.
        :param content_type: "video" or "photo".
        :raises ValueError: On any failure (user-facing message).
        """
        # 1. Resolve brand via domain service
        brand = BrandService.get_default_brand(user)

        # 2. Validate platform connections via domain service
        SocialAccountValidationService.ensure_platforms_connected(brand, platforms)

        # 3. Upload each file to R2
        uploaded_keys = []
        try:
            for idx, media_file in enumerate(media_files):
                file_bytes = media_file.read()
                r2_key = R2StorageService.generate_key(content_type=content_type)
                R2StorageService.upload_file(file_bytes, r2_key, content_type=content_type)
                uploaded_keys.append(r2_key)
        except Exception as e:
            # Clean up any keys that were already uploaded
            for key in uploaded_keys:
                R2StorageService.delete_file(key)
            raise ValueError(f"Failed to upload media: {str(e)}") from e

        # 4. Create ContentPost + ContentMedia + per-platform entries + dispatch Celery tasks
        try:
            with transaction.atomic():
                content_post = ContentPost.objects.create(
                    user=user,
                    brand=brand,
                    title=text or "",
                    description="",
                    content_type=content_type,
                )

                # Create a ContentMedia record for each uploaded file
                ContentMedia.objects.bulk_create([
                    ContentMedia(
                        content_post=content_post,
                        r2_key=r2_key,
                        file_type=content_type,
                        order=idx,
                    )
                    for idx, r2_key in enumerate(uploaded_keys)
                ])

                ContentPostPlatform.objects.bulk_create([
                    ContentPostPlatform(
                        content_post=content_post,
                        platform=platform,
                    )
                    for platform in platforms
                ])

                content_post.refresh_from_db()

                for entry in content_post.platform_entries.all():
                    publish_platform_entry.delay(str(entry.id), content_type=content_type)
        except Exception:
            CustomLogger.exception(
                "content.services.content_creation_service",
                "Failed to dispatch Celery tasks — Redis may be unavailable",
                extra={
                    "r2_keys": uploaded_keys,
                    "platforms": platforms,
                },
            )
            # Clean up R2 files since the DB transaction was rolled back
            for key in uploaded_keys:
                R2StorageService.delete_file(key)
            raise ValueError(
                "Failed to publish content, queue unavailable at the moment. Please try again later."
            )

        return content_post