from celery import shared_task

from content.enums import PostStatus
from content.models import ContentPostPlatform
from content.services.posting_service import PHOTO_PLATFORMS, PostingService
from social_accounts.enums import PlatformChoices
from social_accounts.services.social_account_validation_service import (
    SocialAccountValidationService,
)
from integrations.providers.instagram_service import InstagramService
from utils.custom_logger import CustomLogger


@shared_task
def publish_platform_entry(platform_entry_id, content_type="video"):
    """
    Celery task that publishes a single ContentPostPlatform entry.

    After publishing, checks if all entries for the parent ContentPost
    are done and cleans up the R2 media if so.
    """
    try:
        entry = ContentPostPlatform.objects.select_related(
            "content_post", "content_post__brand"
        ).get(id=platform_entry_id)
    except ContentPostPlatform.DoesNotExist:
        CustomLogger.error(
            "ContentPostPlatform not found for Celery task",
            extra={"platform_entry_id": str(platform_entry_id)},
        )
        return {"status": "error", "message": "ContentPostPlatform not found"}

    result_entry = PostingService.publish_platform_entry(
        entry, content_type=content_type
    )

    if result_entry.status == PostStatus.POSTED:
        PostingService.cleanup_r2_media(result_entry.content_post)
    elif (
        result_entry.status == PostStatus.UPLOADING
        and result_entry.platform == PlatformChoices.INSTAGRAM
    ):
        check_instagram_container_status.delay(result_entry.id)

    return {
        "status": result_entry.status,
        "platform_post_id": result_entry.platform_post_id,
    }


@shared_task(bind=True, max_retries=30, default_retry_delay=10)
def check_instagram_container_status(self, platform_entry_id):
    """
    Celery task that polls the Instagram container status in a non-blocking way.
    Retries itself if processing is still in progress.
    """
    try:
        entry = ContentPostPlatform.objects.select_related(
            "content_post", "content_post__brand"
        ).get(id=platform_entry_id)
    except ContentPostPlatform.DoesNotExist:
        CustomLogger.error(
            "ContentPostPlatform not found for status check",
            extra={"platform_entry_id": str(platform_entry_id)},
        )
        return {"status": "error", "message": "ContentPostPlatform not found"}

    try:
        social_account = SocialAccountValidationService.get_account(
            brand=entry.content_post.brand,
            platform=entry.platform,
        )
        access_token = social_account.get_access_token()
        if not access_token:
            raise ValueError("Unable to obtain a valid access token.")

        status_code = InstagramService.check_container_status(
            access_token=access_token,
            container_id=entry.platform_post_id,
        )

        if status_code == "FINISHED":
            # Publish the container
            publish_result = InstagramService.publish_container(
                access_token=access_token,
                instagram_account_id=social_account.external_id,
                container_id=entry.platform_post_id,
            )
            # Update the entry to POSTED
            entry.status = PostStatus.POSTED
            entry.platform_post_id = publish_result.get(
                "platform_post_id", entry.platform_post_id
            )
            entry.save(update_fields=["status", "platform_post_id", "updated_at"])

            # Clean up R2 media if everything is posted
            PostingService.cleanup_r2_media(entry.content_post)

            return {
                "status": "posted",
                "platform_post_id": entry.platform_post_id,
            }

        elif status_code == "IN_PROGRESS":
            # Queue a retry of this task
            raise self.retry()

        else:
            raise ValueError(f"Unexpected status code: {status_code}")

    except Exception as e:
        from celery.exceptions import Retry

        if isinstance(e, Retry):
            raise e

        CustomLogger.exception(
            "Instagram status check failed",
            extra={"platform_entry_id": str(platform_entry_id)},
        )

        if self.request.retries >= self.max_retries:
            entry.status = PostStatus.FAILED
            entry.error_message = (
                f"Instagram processing timed out or failed: {str(e)}"
            )
            entry.save(update_fields=["status", "error_message", "updated_at"])
            PostingService.cleanup_r2_media(entry.content_post)
            raise e
        else:
            raise self.retry(exc=e)
