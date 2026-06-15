"""
Service for creating ContentPost records from an incoming request,
including brand resolution, platform validation, R2 upload, and Celery dispatch.

Delegates cross-domain queries to BrandService and SocialAccountValidationService.
"""

from typing import List

from content.models import ContentPost, ContentPostPlatform
from users.services.brand_service import BrandService
from social_accounts.services.social_account_validation_service import SocialAccountValidationService
from utils.r2_storage import R2StorageService


class ContentCreationService:
    """
    Handles the full creation and publishing pipeline:
    validate inputs, resolve brand and platform connections, upload to R2,
    create DB records, and dispatch Celery tasks for each platform.
    """

    @classmethod
    def create_content_post(
        cls,
        *,
        user,
        media_file,
        text: str,
        platforms: List[str],
        content_type: str = "video",
    ) -> ContentPost:
        """
        Full creation + dispatch pipeline:
        1. Resolve the user's default brand (via BrandService)
        2. Validate every requested platform has a connected SocialAccount
        3. Upload the media to R2
        4. Create ContentPost + ContentPostPlatform entries
        5. Dispatch a Celery task for each platform entry

        Raises ValueError with a user-facing message on failure.
        """
        # 1. Resolve brand via domain service
        brand = BrandService.get_default_brand(user)

        # 2. Validate platform connections via domain service
        SocialAccountValidationService.ensure_platforms_connected(brand, platforms)

        # 3. Upload to R2
        try:
            file_bytes = media_file.read()
            r2_key = R2StorageService.generate_key(prefix="content")
            R2StorageService.upload_file(file_bytes, r2_key)
        except Exception as e:
            raise ValueError(f"Failed to upload media: {str(e)}") from e

        # 4. Create ContentPost + per-platform entries
        content_post = ContentPost.objects.create(
            user=user,
            brand=brand,
            title=text or "",
            description="",
            video_r2_key=r2_key,
        )

        ContentPostPlatform.objects.bulk_create([
            ContentPostPlatform(
                content_post=content_post,
                platform=platform,
            )
            for platform in platforms
        ])

        content_post.refresh_from_db()

        # 5. Dispatch Celery tasks for each platform
        # Import here to avoid circular import at module level
        from content.tasks import publish_platform_entry

        for entry in content_post.platform_entries.all():
            publish_platform_entry.delay(str(entry.id), content_type=content_type)

        return content_post