from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from content.enums import FileTypeChoice, PostStatus
from content.models import ContentPostPlatform
from content.services.content_post_service import ContentPostService
from content.services.posting_service import PostingService
from integrations.providers.instagram_service import InstagramService
from integrations.providers.tiktok_service import TiktokService
from social_accounts.enums import PlatformChoices
from social_accounts.services.social_account_validation_service import (
    SocialAccountValidationService,
)
from utils.custom_logger import CustomLogger
from utils.r2_storage import R2StorageService


@shared_task(bind=True, max_retries=5, default_retry_delay=1, acks_late=True)
def wait_for_media_and_publish_platform_entry(
    self, platform_entry_id, content_type="video"
):
    """
    Waits for R2 media to become accessible (with its own retry budget),
    then hands off to publish_platform_entry.
    """
    try:
        entry = ContentPostPlatform.objects.select_related(
            "content_post", "content_post__brand"
        ).get(id=platform_entry_id)
    except ContentPostPlatform.DoesNotExist:
        CustomLogger.error(
            "ContentPostPlatform not found for media availability check",
            extra={"platform_entry_id": str(platform_entry_id)},
        )
        return

    content_post = entry.content_post
    files_to_check = []

    if content_type == "photo":
        photos = ContentPostService.get_media_items(
            content_post, file_type=FileTypeChoice.IMAGE
        )
        files_to_check = [item.r2_key for item in photos]
    else:
        videos = ContentPostService.get_media_items(
            content_post, file_type=FileTypeChoice.VIDEO
        )
        video_item = videos.first()
        if video_item:
            files_to_check.append(video_item.r2_key)
        if content_post.thumbnail_r2_key:
            files_to_check.append(content_post.thumbnail_r2_key)

    for r2_key in files_to_check:
        if not R2StorageService.is_file_accessible(r2_key):
            # retry count as 1sec, 2sec etc
            countdown = self.request.retries + 1
            CustomLogger.info(
                "Media file not yet accessible, retrying availability check",
                extra={
                    "platform_entry_id": str(entry.id),
                    "r2_key": r2_key,
                    "attempt": self.request.retries + 1,
                    "max_retries": self.max_retries,
                    "retry_in_seconds": countdown,
                },
            )
            raise self.retry(countdown=countdown)

    CustomLogger.info(
        "Media confirmed accessible, triggering publish",
        extra={"platform_entry_id": str(entry.id)},
    )
    publish_platform_entry.delay(str(entry.id), content_type=content_type)


@shared_task(bind=True, max_retries=5, default_retry_delay=1, acks_late=True)
def publish_platform_entry(self, platform_entry_id, content_type="video"):
    """
    Celery task that publishes a single ContentPostPlatform entry.

    After publishing, checks if all entries for the parent ContentPost
    are done and cleans up the R2 media if so.
    """
    CustomLogger.info(
        "publish_platform_entry task triggered",
        extra={
            "platform_entry_id": str(platform_entry_id),
            "content_type": content_type,
            "attempt": self.request.retries + 1,
        },
    )
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

    try:
        result_entry = PostingService.publish_platform_entry(
            entry, content_type=content_type
        )
    except Exception as exc:
        CustomLogger.exception(
            "Transient exception during publish task, retrying",
            extra={"platform_entry_id": str(platform_entry_id)},
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

    if result_entry.status == PostStatus.FAILED:
        # Check if error is transient (connection/network issues or 5xx HTTP codes)
        transient_keywords = [
            "connection",
            "forcibly closed",
            "timeout",
            "500",
            "502",
            "503",
            "504",
            "bad gateway",
            "unable to fetch",
            "temporarily unavailable",
            "please try again",
            "internal server error",
        ]
        if any(kw in result_entry.error_message.lower() for kw in transient_keywords):
            CustomLogger.warning(
                "Transient failure detected, retrying publish task",
                extra={
                    "platform_entry_id": str(platform_entry_id),
                    "error_message": result_entry.error_message,
                    "retry_count": self.request.retries,
                },
            )
            # Revert status to PENDING before retrying
            result_entry.status = PostStatus.PENDING
            result_entry.save(update_fields=["status", "updated_at"])
            raise self.retry(countdown=60 * (self.request.retries + 1))

    if result_entry.status == PostStatus.POSTED:
        PostingService.cleanup_r2_media(result_entry.content_post)
    elif result_entry.status == PostStatus.PROCESSING:
        if result_entry.platform == PlatformChoices.INSTAGRAM:
            CustomLogger.info(
                "Triggering check_instagram_container_status",
                extra={"platform_entry_id": str(result_entry.id)},
            )
            check_instagram_container_status.delay(str(result_entry.id))
        elif result_entry.platform == PlatformChoices.TIKTOK:
            CustomLogger.info(
                "Triggering check_tiktok_publish_status",
                extra={"platform_entry_id": str(result_entry.id)},
            )
            check_tiktok_publish_status.delay(str(result_entry.id))

    return {
        "status": result_entry.status,
        "platform_post_id": result_entry.platform_post_id,
    }


@shared_task(bind=True, max_retries=30, default_retry_delay=10, acks_late=True)
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

            # Fetch the permalink
            try:
                entry.post_url = InstagramService.get_permalink(
                    access_token=access_token, media_id=entry.platform_post_id
                )
            except Exception as e:
                CustomLogger.warning(
                    "Failed to fetch permalink for newly published media",
                    extra={"media_id": entry.platform_post_id, "error": str(e)},
                )

            entry.save(
                update_fields=["status", "platform_post_id", "post_url", "updated_at"]
            )

            # Clean up R2 media if everything is posted
            PostingService.cleanup_r2_media(entry.content_post)

            return {
                "status": "posted",
                "platform_post_id": entry.platform_post_id,
            }

        elif status_code == "PUBLISHED":
            # The container was already published (perhaps a previous attempt succeeded but timed out locally)
            entry.status = PostStatus.POSTED

            entry.save(update_fields=["status", "updated_at"])
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
            entry.error_message = f"Instagram processing timed out or failed: {str(e)}"
            entry.save(update_fields=["status", "error_message", "updated_at"])
            PostingService.cleanup_r2_media(entry.content_post)
            raise e
        else:
            raise self.retry(exc=e)


@shared_task(bind=True, max_retries=30, default_retry_delay=10, acks_late=True)
def check_tiktok_publish_status(self, platform_entry_id):
    """
    Celery task that polls the TikTok publish status in a non-blocking way.
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

        status_data = TiktokService.check_publish_status(
            access_token=access_token,
            publish_id=entry.platform_post_id,
        )

        status_val = status_data.get("status")

        if status_val == "PUBLISH_COMPLETE":
            public_post_ids = status_data.get("publicaly_available_post_id", [])
            final_post_id = (
                public_post_ids[0] if public_post_ids else entry.platform_post_id
            )

            entry.status = PostStatus.POSTED
            entry.platform_post_id = final_post_id

            username = social_account.account_name or social_account.external_id
            entry.post_url = f"https://www.tiktok.com/@{username}/video/{final_post_id}"

            entry.save(
                update_fields=["status", "platform_post_id", "post_url", "updated_at"]
            )

            PostingService.cleanup_r2_media(entry.content_post)

            return {
                "status": "posted",
                "platform_post_id": final_post_id,
            }

        elif status_val == "FAILED":
            raise ValueError(status_data.get("fail_reason", "Unknown TikTok error"))

        else:
            # e.g., PROCESSING_DOWNLOAD, PROCESSING
            raise self.retry()

    except Exception as e:
        from celery.exceptions import Retry

        if isinstance(e, Retry):
            raise e

        CustomLogger.exception(
            "TikTok status check failed",
            extra={"platform_entry_id": str(platform_entry_id)},
        )

        if self.request.retries >= self.max_retries or (
            isinstance(e, ValueError) and "TikTok status check failed" not in str(e)
        ):
            # If it's a direct FAILED status from TikTok, we don't retry, or if we exhaust retries
            entry.status = PostStatus.FAILED
            entry.error_message = f"TikTok processing failed: {str(e)}"
            entry.save(update_fields=["status", "error_message", "updated_at"])
            PostingService.cleanup_r2_media(entry.content_post)
            # Do not raise the exception so we don't retry
            return {"status": "failed", "message": str(e)}
        else:
            raise self.retry(exc=e)


@shared_task
def publish_scheduled_posts():
    """
    Periodic task to check for scheduled posts that are due to be published.
    """
    now = timezone.now()
    due_entries = ContentPostPlatform.objects.filter(
        status=PostStatus.SCHEDULED, content_post__scheduled_at__lte=now
    ).select_related("content_post")

    count = due_entries.count()
    if count > 0:
        CustomLogger.info(f"Found {count} scheduled posts due to be published.")

    processed_count = 0
    for entry in due_entries:
        try:
            with transaction.atomic():
                locked_entry = ContentPostPlatform.objects.select_for_update().get(
                    id=entry.id
                )
                if locked_entry.status == PostStatus.SCHEDULED:
                    locked_entry.status = PostStatus.PENDING
                    locked_entry.save(update_fields=["status", "updated_at"])

                    wait_for_media_and_publish_platform_entry.delay(
                        str(locked_entry.id),
                        content_type=locked_entry.content_post.content_type,
                    )
                    processed_count += 1
        except Exception as e:
            CustomLogger.exception(
                "Error processing scheduled post platform entry",
                extra={"platform_entry_id": str(entry.id), "error": str(e)},
            )

    return f"Processed {processed_count} posts"


@shared_task
def sweep_stuck_platform_entries():
    """
    Periodic task to sweep for posts that have been stuck in PENDING or UPLOADING
    status for more than 2 hours. Marks them as FAILED to prevent indefinite hanging
    and accidental double-posting later.
    """
    now = timezone.now()
    two_hours_ago = now - timedelta(hours=2)

    stuck_entries = ContentPostPlatform.objects.filter(
        status__in=[PostStatus.PENDING, PostStatus.UPLOADING, PostStatus.PROCESSING],
        updated_at__lte=two_hours_ago,
        content_post__scheduled_at__isnull=False,
    )

    for entry in stuck_entries:
        try:
            with transaction.atomic():
                locked_entry = ContentPostPlatform.objects.select_for_update().get(
                    id=entry.id
                )
                # Double check they are still stuck
                if locked_entry.status in [
                    PostStatus.PENDING,
                    PostStatus.UPLOADING,
                    PostStatus.PROCESSING,
                ]:
                    locked_entry.status = PostStatus.FAILED
                    locked_entry.error_message = (
                        "System interrupted during posting. Please try again."
                    )
                    locked_entry.save(
                        update_fields=["status", "error_message", "updated_at"]
                    )
                    CustomLogger.warning(
                        "Swept stuck platform entry and marked as FAILED.",
                        extra={
                            "platform_entry_id": str(locked_entry.id),
                            "status_was": locked_entry.status,
                        },
                    )
        except Exception as e:
            CustomLogger.exception(
                "Error sweeping stuck platform entry",
                extra={"platform_entry_id": str(entry.id), "error": str(e)},
            )
