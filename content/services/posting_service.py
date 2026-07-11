"""
Orchestrates publishing a ContentPostPlatform entry to its target platform.
Supports both video and photo content types.
"""

from content.enums import FileTypeChoice, PostStatus
from content.models import ContentPostPlatform
from content.services.content_post_service import ContentPostService
from integrations.providers.facebook_service import FacebookService
from integrations.providers.instagram_service import InstagramService
from integrations.providers.linkedin_service import LinkedinService
from integrations.providers.tiktok_service import TiktokService
from integrations.providers.youtube_service import YoutubeService
from social_accounts.enums import PlatformChoices
from social_accounts.services.social_account_validation_service import (
    SocialAccountValidationService,
)
from utils.custom_logger import CustomLogger
from utils.r2_storage import R2StorageService

# Platforms that need raw bytes (for video)
BYTES_PLATFORMS = {PlatformChoices.YOUTUBE}

# Platforms that need a presigned URL
URL_PLATFORMS = {
    PlatformChoices.TIKTOK,
    PlatformChoices.FACEBOOK,
    PlatformChoices.INSTAGRAM,
    PlatformChoices.LINKEDIN,
}
# Platforms that support photo posting
PHOTO_PLATFORMS = {
    PlatformChoices.FACEBOOK,
    PlatformChoices.INSTAGRAM,
    PlatformChoices.TIKTOK,
    PlatformChoices.LINKEDIN,
}


class PostingService:
    """
    Stateless service that publishes a ContentPostPlatform to its target platform.
    All public methods are staticmethods.
    """

    @classmethod
    def publish_platform_entry(
        cls,
        entry: ContentPostPlatform,
        content_type: str = "video",
    ) -> ContentPostPlatform:
        """
        Publish a single ContentPostPlatform.

        :param entry: The platform entry to publish.
        :param content_type: "video" or "photo".
        """
        content_post = entry.content_post

        try:
            social_account = SocialAccountValidationService.get_account(
                brand=content_post.brand,
                platform=entry.platform,
            )

            access_token = social_account.get_access_token()
            if not access_token:
                raise ValueError(
                    f"Unable to obtain a valid access token for {entry.platform}."
                )

            entry.status = PostStatus.UPLOADING
            entry.save(update_fields=["status", "updated_at"])

            presigned_url = None
            media_bytes = None

            # Photo platforms need URLs for each image; video platforms vary
            needs_url = content_type == "photo" or entry.platform in URL_PLATFORMS
            needs_bytes = content_type == "video" and entry.platform in BYTES_PLATFORMS

            if content_type == "photo":
                # Generate a presigned URL for each image
                image_items = ContentPostService.get_media_items(
                    content_post, file_type=FileTypeChoice.IMAGE
                )
                presigned_urls = [
                    R2StorageService.generate_presigned_url(
                        item.r2_key, expiration=7200
                    )
                    for item in image_items
                ]
                if not presigned_urls or any(url is None for url in presigned_urls):
                    CustomLogger.error(
                        "content.services.posting_service",
                        "Failed to generate presigned URLs for photos",
                        extra={
                            "content_post_id": str(content_post.id),
                        },
                    )
                    raise ValueError("Failed to generate presigned URLs for photos")
            elif needs_url:
                # Single video → single presigned URL
                video_items = ContentPostService.get_media_items(
                    content_post, file_type=FileTypeChoice.VIDEO
                )
                video_item = video_items.first()
                if not video_item:
                    CustomLogger.error(
                        "content.services.posting_service",
                        "No video media found for this post",
                        extra={
                            "content_post_id": str(content_post.id),
                        },
                    )
                    raise ValueError("No video media found for this post")
                presigned_url = R2StorageService.generate_presigned_url(
                    video_item.r2_key, expiration=7200
                )
                if not presigned_url:
                    raise ValueError("Failed to generate presigned URL")

            if needs_bytes:
                video_items = ContentPostService.get_media_items(
                    content_post, file_type=FileTypeChoice.VIDEO
                )
                video_item = video_items.first()
                if not video_item:
                    raise ValueError("No video media found for this post")
                media_bytes = R2StorageService.download_file(video_item.r2_key)

            if content_type == "photo":
                result = cls._dispatch_photo(
                    platform=entry.platform,
                    access_token=access_token,
                    social_account=social_account,
                    photo_urls=presigned_urls,
                    text=entry.caption,
                )
            else:
                result = cls._dispatch_video(
                    platform=entry.platform,
                    access_token=access_token,
                    social_account=social_account,
                    media_bytes=media_bytes,
                    video_url=presigned_url or "",
                    title=entry.title,
                    description=entry.caption,
                )

            if result.get("status") == "processing":
                entry.status = PostStatus.UPLOADING
            else:
                entry.status = PostStatus.POSTED
            entry.platform_post_id = result.get("platform_post_id", "")
            entry.save(update_fields=["status", "platform_post_id", "updated_at"])

        except Exception as e:
            CustomLogger.exception(
                "Platform publish failed",
                extra={
                    "content_post_platform_id": str(entry.id),
                    "platform": entry.platform,
                    "content_type": content_type,
                },
            )
            entry.status = PostStatus.FAILED
            entry.error_message = str(e)
            entry.save(update_fields=["status", "error_message", "updated_at"])

        return entry

    @classmethod
    def cleanup_r2_media(cls, content_post) -> None:
        if ContentPostService.has_pending_entries(content_post):
            return

        for media_item in content_post.media_items.all():
            R2StorageService.delete_file(media_item.r2_key)

    # ── private helpers ────────────────────────────────────

    @classmethod
    def _dispatch_video(
        cls,
        platform,
        access_token,
        social_account,
        media_bytes,
        video_url,
        title,
        description,
    ) -> dict:
        if platform == PlatformChoices.YOUTUBE:
            return YoutubeService.publish_video(
                access_token=access_token,
                video_bytes=media_bytes,
                title=title,
                description=description,
            )
        if platform == PlatformChoices.TIKTOK:
            return TiktokService.publish_video(
                access_token=access_token,
                video_url=video_url,
                title=description,  # TikTok caption is passed in 'title'
            )
        if platform == PlatformChoices.FACEBOOK:
            return FacebookService.publish_video(
                page_access_token=access_token,
                page_id=social_account.external_id,
                video_url=video_url,
                title=title,
                description=description,
            )
        if platform == PlatformChoices.INSTAGRAM:
            return InstagramService.publish_video(
                access_token=access_token,
                instagram_account_id=social_account.external_id,
                video_url=video_url,
                caption=description,
            )
        if platform == PlatformChoices.LINKEDIN:
            return LinkedinService.publish_video(
                access_token=access_token,
                person_urn=f"urn:li:person:{social_account.external_id}",
                video_url=video_url,
                title=title,
                description=description,
            )
        raise ValueError(f"Video publishing not supported for: {platform}")

    @classmethod
    def _dispatch_photo(
        cls, platform, access_token, social_account, photo_urls, text
    ) -> dict:
        if platform == PlatformChoices.FACEBOOK:
            return FacebookService.publish_photo(
                page_access_token=access_token,
                page_id=social_account.external_id,
                photo_urls=photo_urls,
                text=text,
            )
        if platform == PlatformChoices.INSTAGRAM:
            return InstagramService.publish_photo(
                access_token=access_token,
                instagram_account_id=social_account.external_id,
                photo_urls=photo_urls,
                caption=text,
            )
        if platform == PlatformChoices.TIKTOK:
            return TiktokService.publish_photo(
                access_token=access_token,
                photo_urls=photo_urls,
                text=text,
            )
        if platform == PlatformChoices.LINKEDIN:
            return LinkedinService.publish_photo(
                access_token=access_token,
                person_urn=f"urn:li:person:{social_account.external_id}",
                photo_urls=photo_urls,
                text=text,
            )
        raise ValueError(f"Photo publishing not supported for: {platform}")
