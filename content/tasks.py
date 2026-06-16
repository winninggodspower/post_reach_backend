from celery import shared_task

from content.models import ContentPostPlatform
from content.services.posting_service import PostingService, PHOTO_PLATFORMS
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

    result_entry = PostingService.publish_platform_entry(entry, content_type=content_type)

    PostingService.cleanup_r2_media(result_entry.content_post)

    return {
        "status": result_entry.status,
        "platform_post_id": result_entry.platform_post_id,
    }
