"""
Orchestrates publishing a ContentPostPlatform entry to its target platform.
Supports both video and photo content types.
"""

from content.enums import PostStatus
from content.models import ContentPostPlatform
from integrations.providers.facebook_service import FacebookService
from integrations.providers.instagram_service import InstagramService
from integrations.providers.linkedin_service import LinkedinService
from integrations.providers.tiktok_service import TiktokService
from integrations.providers.youtube_service import YoutubeService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount
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
            social_account = cls._resolve_social_account(
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
            video_bytes = None

            # Photo platforms need a URL; video platforms vary
            needs_url = (
                content_type == "photo"
                or entry.platform in URL_PLATFORMS
            )
            needs_bytes = (
                content_type == "video"
                and entry.platform in BYTES_PLATFORMS
            )

            if needs_url:
                presigned_url = R2StorageService.generate_presigned_url(
                    content_post.video_r2_key, expiration=7200
                )
                if not presigned_url:
                    raise ValueError("Failed to generate presigned URL")

            if needs_bytes:
                video_bytes = cls._download_video_from_r2(content_post.video_r2_key)

            if content_type == "photo":
                result = cls._dispatch_photo(
                    platform=entry.platform,
                    access_token=access_token,
                    social_account=social_account,
                    photo_url=presigned_url,
                    text=content_post.title,
                )
            else:
                result = cls._dispatch_video(
                    platform=entry.platform,
                    access_token=access_token,
                    social_account=social_account,
                    video_bytes=video_bytes,
                    video_url=presigned_url or "",
                    title=content_post.title,
                    description=content_post.description,
                )

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
    def cleanup_r2_video(cls, content_post) -> None:
        pending = content_post.platform_entries.filter(
            status__in=[PostStatus.PENDING, PostStatus.UPLOADING]
        ).exists()
        if not pending:
            R2StorageService.delete_file(content_post.video_r2_key)

    # ── private helpers ────────────────────────────────────

    @classmethod
    def _resolve_social_account(cls, brand, platform: str) -> SocialAccount:
        try:
            return SocialAccount.objects.get(brand=brand, platform=platform)
        except SocialAccount.DoesNotExist:
            raise ValueError(
                f"No connected {platform} account found for brand '{brand.name}'."
            )

    @classmethod
    def _download_video_from_r2(cls, key: str) -> bytes:
        client = R2StorageService._get_client()
        from django.conf import settings

        try:
            response = client.get_object(
                Bucket=settings.CLOUDFLARE_R2_BUCKET,
                Key=key,
            )
            return response["Body"].read()
        except Exception as e:
            raise ValueError(f"Failed to download video from R2: {str(e)}") from e

    @classmethod
    def _dispatch_video(
        cls, platform, access_token, social_account, video_bytes, video_url, title, description
    ) -> dict:
        if platform == PlatformChoices.YOUTUBE:
            return YoutubeService.publish_video(
                access_token=access_token,
                video_bytes=video_bytes,
                title=title,
                description=description,
            )
        if platform == PlatformChoices.TIKTOK:
            return TiktokService.publish_video(
                access_token=access_token,
                video_url=video_url,
                title=title,
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
                caption=title,
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
        cls, platform, access_token, social_account, photo_url, text
    ) -> dict:
        if platform == PlatformChoices.FACEBOOK:
            return FacebookService.publish_photo(
                page_access_token=access_token,
                page_id=social_account.external_id,
                photo_url=photo_url,
                text=text,
            )
        if platform == PlatformChoices.INSTAGRAM:
            return InstagramService.publish_photo(
                access_token=access_token,
                instagram_account_id=social_account.external_id,
                photo_url=photo_url,
                caption=text,
            )
        if platform == PlatformChoices.TIKTOK:
            return TiktokService.publish_photo(
                access_token=access_token,
                photo_url=photo_url,
                text=text,
            )
        if platform == PlatformChoices.LINKEDIN:
            return LinkedinService.publish_photo(
                access_token=access_token,
                person_urn=f"urn:li:person:{social_account.external_id}",
                photo_url=photo_url,
                text=text,
            )
        raise ValueError(f"Photo publishing not supported for: {platform}")