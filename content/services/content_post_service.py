"""
Service layer for ContentPost model queries.
Encapsulates all direct ContentPost model access so views and other services
never import from content.models directly.
"""

from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from content.enums import FileTypeChoice, PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from social_accounts.services.social_account_validation_service import (
    SocialAccountValidationService,
)
from users.models import User
from users.services.brand_service import BrandService
from utils.custom_logger import CustomLogger, log_exceptions
from utils.r2_storage import R2StorageService


class ContentPostService:
    """
    Stateless service for querying ContentPost records.
    All public methods are classmethods.
    """

    @classmethod
    @log_exceptions()
    def create_content_post(
        cls,
        *,
        user,
        media_keys: list[str] = None,
        caption: str = "",
        platforms: list[str],
        platform_settings: dict = None,
        content_type: str = "video",
        scheduled_at=None,
        thumbnail_key: str = None,
        video_thumbnail_offset=None,
    ) -> ContentPost:
        """
        Full creation + dispatch pipeline:
        1. Resolve the user's default brand (via BrandService)
        2. Validate every requested platform has a connected SocialAccount
        3. Upload each media file to R2 (videos go to videos/ folder, photos to photos/)
        4. Create ContentPost + ContentMedia + ContentPostPlatform entries
        5. Dispatch a Celery task for each platform entry (if not scheduled)

        :param media_files: List of Django UploadedFile objects.
        :param content_type: "video" or "photo".
        :raises ValueError: On any failure (user-facing message).
        """
        platform_settings = platform_settings or {}

        # 1. Resolve brand via domain service
        brand = BrandService.get_default_brand(user)

        # 2. Validate platform connections via domain service
        SocialAccountValidationService.ensure_platforms_connected(brand, platforms)

        media_keys = media_keys or []
        thumbnail_key = thumbnail_key or ""

        # 4. Create ContentPost + ContentMedia + per-platform entries + dispatch Celery tasks
        try:
            with transaction.atomic():
                content_post = ContentPost.objects.create(
                    user=user,
                    brand=brand,
                    caption=caption or "",
                    content_type=content_type,
                    scheduled_at=scheduled_at,
                    thumbnail_r2_key=thumbnail_key,
                    video_thumbnail_offset=video_thumbnail_offset,
                )

                # Create a ContentMedia record for each uploaded file
                if content_type != "text":
                    ContentMedia.objects.bulk_create(
                        [
                            ContentMedia(
                                content_post=content_post,
                                r2_key=r2_key,
                                file_type=(
                                    FileTypeChoice.IMAGE
                                    if content_type == "photo"
                                    else FileTypeChoice.VIDEO
                                ),
                                order=idx,
                            )
                            for idx, r2_key in enumerate(media_keys)
                        ]
                    )

                platform_entries = []
                initial_status = (
                    PostStatus.SCHEDULED if scheduled_at else PostStatus.PENDING
                )

                for platform in platforms:
                    plat_settings = platform_settings.get(platform, {})
                    if platform == "youtube":
                        title = plat_settings.get("title", "")
                        plat_caption = plat_settings.get(
                            "description", plat_settings.get("caption", caption)
                        )
                    else:
                        title = ""
                        plat_caption = plat_settings.get("caption", caption)

                    platform_entries.append(
                        ContentPostPlatform(
                            content_post=content_post,
                            platform=platform,
                            title=title,
                            caption=plat_caption,
                            status=initial_status,
                            settings=plat_settings,
                        )
                    )

                ContentPostPlatform.objects.bulk_create(platform_entries)

                content_post.refresh_from_db()

                if not scheduled_at:
                    from content.tasks import wait_for_media_and_publish_platform_entry

                    for entry in content_post.platform_entries.all():

                        def dispatch_task(e_id=str(entry.id), c_type=content_type):
                            CustomLogger.info(
                                "Django app dispatching wait_for_media_and_publish_platform_entry to Celery",
                                extra={
                                    "platform_entry_id": e_id,
                                    "content_type": c_type,
                                },
                            )
                            wait_for_media_and_publish_platform_entry.delay(
                                e_id, content_type=c_type
                            )

                        transaction.on_commit(dispatch_task)
        except Exception:
            CustomLogger.exception(
                "content.services.content_post_service",
                "Failed to dispatch Celery tasks — Redis may be unavailable",
                extra={
                    "r2_keys": media_keys,
                    "platforms": platforms,
                },
            )
            raise ValueError(
                "Failed to publish content, queue unavailable at the moment. Please try again later."
            )

        return content_post

    @classmethod
    def get_content_post(cls, post_id: UUID, user: User) -> ContentPost:
        """
        Retrieve a single ContentPost by ID, ensuring it belongs to the given user.
        Prefetches platform_entries for efficiency.

        :raises ContentPost.DoesNotExist: If not found or not owned by user.
        :return: The ContentPost instance.
        """
        return (
            ContentPost.objects.select_related("brand")
            .prefetch_related(
                Prefetch(
                    "media_items",
                    queryset=ContentMedia.objects.order_by("order"),
                ),
                Prefetch(
                    "platform_entries",
                    queryset=ContentPostPlatform.objects.all(),
                ),
            )
            .get(id=post_id, user=user)
        )

    @classmethod
    def get_scheduled_posts(
        cls,
        *,
        brand,
        platform: str = None,
        content_type: str = None,
        limit: int = None,
    ):
        """
        Retrieves future scheduled posts for a brand that are pending publication.
        Ordered chronologically (earliest scheduled date first).
        """
        now = timezone.now()
        qs = (
            ContentPost.objects.filter(
                brand=brand,
                scheduled_at__gt=now,
                platform_entries__status=PostStatus.SCHEDULED,
            )
            .distinct()
            .select_related("brand")
            .prefetch_related(
                Prefetch(
                    "media_items",
                    queryset=ContentMedia.objects.order_by("order"),
                ),
                Prefetch(
                    "platform_entries",
                    queryset=ContentPostPlatform.objects.all(),
                ),
            )
            .order_by("scheduled_at")
        )

        if platform:
            qs = qs.filter(platform_entries__platform=platform)

        if content_type:
            qs = qs.filter(content_type=content_type)

        if limit and limit > 0:
            qs = qs[:limit]

        return qs

    @classmethod
    def get_media_items(
        cls, content_post: ContentPost, file_type: str = FileTypeChoice.IMAGE
    ):
        """
        Get media items for a post filtered by file_type, ordered by position.
        """
        return content_post.media_items.filter(file_type=file_type).order_by("order")

    @classmethod
    def has_pending_entries(cls, content_post: ContentPost) -> bool:
        """
        Check if any platform entry for this post is still pending or uploading.
        """

        return content_post.platform_entries.filter(
            status__in=[
                PostStatus.PENDING,
                PostStatus.SCHEDULED,
                PostStatus.UPLOADING,
                PostStatus.PROCESSING,
            ]
        ).exists()

    @classmethod
    def update_content_post(
        cls, content_post: ContentPost, validated_data: dict
    ) -> ContentPost:
        """
        Update caption, scheduled_at, platform settings, and platforms list for a content post.
        Only allowed if ALL platform entries are still PENDING or SCHEDULED.
        """
        # Ensure all entries are PENDING or SCHEDULED before allowing updates
        for entry in content_post.platform_entries.all():
            if entry.status not in [PostStatus.PENDING, PostStatus.SCHEDULED]:
                raise ValueError(
                    f"Cannot update post because platform '{entry.platform}' is in status '{entry.status}'. "
                    "Only fully pending or scheduled posts can be updated."
                )

        save_post = False
        if "caption" in validated_data:
            content_post.caption = validated_data["caption"]
            save_post = True

        if "scheduled_at" in validated_data:
            new_scheduled_at = validated_data["scheduled_at"]
            if content_post.scheduled_at != new_scheduled_at:
                old_scheduled_at = content_post.scheduled_at
                content_post.scheduled_at = new_scheduled_at
                save_post = True

                # Update status of all existing entries to reflect the new schedule
                new_status = (
                    PostStatus.SCHEDULED if new_scheduled_at else PostStatus.PENDING
                )

                # Bulk update to avoid multiple DB hits
                ContentPostPlatform.objects.filter(
                    content_post=content_post,
                    status__in=[PostStatus.PENDING, PostStatus.SCHEDULED],
                ).update(status=new_status)

                # If they just changed it from Scheduled to Immediate (None), we need to dispatch tasks
                if not new_scheduled_at and old_scheduled_at:
                    from content.tasks import wait_for_media_and_publish_platform_entry

                    # Re-fetch the entries we just updated to pending
                    immediate_entries = ContentPostPlatform.objects.filter(
                        content_post=content_post, status=PostStatus.PENDING
                    )
                    for entry in immediate_entries:

                        def dispatch_task(
                            e_id=str(entry.id), c_type=content_post.content_type
                        ):
                            wait_for_media_and_publish_platform_entry.delay(
                                e_id, content_type=c_type
                            )

                        transaction.on_commit(dispatch_task)

        if save_post:
            content_post.save()

        with transaction.atomic():
            platforms_to_add = set()
            if "platforms" in validated_data:
                new_platform_set = set(validated_data["platforms"])
                existing_platform_set = {
                    entry.platform for entry in content_post.platform_entries.all()
                }

                platforms_to_add = new_platform_set - existing_platform_set
                platforms_to_remove = existing_platform_set - new_platform_set

                if platforms_to_add:
                    SocialAccountValidationService.ensure_platforms_connected(
                        content_post.brand, list(platforms_to_add)
                    )

                    initial_status = (
                        PostStatus.SCHEDULED
                        if content_post.scheduled_at
                        else PostStatus.PENDING
                    )
                    platform_settings = validated_data.get("platform_settings", {})
                    new_entries = []

                    for platform in platforms_to_add:
                        plat_settings = platform_settings.get(platform, {})
                        if platform == "youtube":
                            title = plat_settings.get("title", "")
                            plat_caption = plat_settings.get(
                                "description",
                                plat_settings.get("caption", content_post.caption),
                            )
                        else:
                            title = ""
                            plat_caption = plat_settings.get(
                                "caption", content_post.caption
                            )

                        new_entries.append(
                            ContentPostPlatform(
                                content_post=content_post,
                                platform=platform,
                                title=title,
                                caption=plat_caption,
                                status=initial_status,
                                settings=plat_settings,
                            )
                        )
                    ContentPostPlatform.objects.bulk_create(new_entries)

                    # If this post is supposed to go out immediately (not scheduled), we need to dispatch Celery tasks
                    if not content_post.scheduled_at:
                        from content.tasks import (
                            wait_for_media_and_publish_platform_entry,
                        )

                        newly_created = ContentPostPlatform.objects.filter(
                            content_post=content_post, platform__in=platforms_to_add
                        )
                        for entry in newly_created:

                            def dispatch_task(
                                e_id=str(entry.id), c_type=content_post.content_type
                            ):
                                wait_for_media_and_publish_platform_entry.delay(
                                    e_id, content_type=c_type
                                )

                            transaction.on_commit(dispatch_task)

                if platforms_to_remove:
                    content_post.platform_entries.filter(
                        platform__in=platforms_to_remove
                    ).delete()

            # Update settings, caption, and title on existing platform entries
            caption_updated = "caption" in validated_data
            platform_settings = validated_data.get("platform_settings", {})

            # Query all current entries except newly created ones (which were already initialized with latest values)
            entries_to_update = content_post.platform_entries.exclude(
                platform__in=platforms_to_add
            )
            for entry in entries_to_update:
                save_entry = False
                plat_settings = platform_settings.get(entry.platform)

                if plat_settings:
                    current_settings = entry.settings or {}
                    current_settings.update(plat_settings)
                    entry.settings = current_settings
                    save_entry = True

                if entry.platform == "youtube":
                    if plat_settings and "title" in plat_settings:
                        entry.title = plat_settings["title"]
                        save_entry = True
                    if plat_settings and (
                        "description" in plat_settings or "caption" in plat_settings
                    ):
                        entry.caption = plat_settings.get(
                            "description", plat_settings.get("caption")
                        )
                        save_entry = True
                    elif caption_updated:
                        entry.caption = content_post.caption
                        save_entry = True
                else:
                    if plat_settings and "caption" in plat_settings:
                        entry.caption = plat_settings["caption"]
                        save_entry = True
                    elif caption_updated:
                        entry.caption = content_post.caption
                        save_entry = True

                if save_entry:
                    entry.save()

        # Re-fetch the content_post from DB to ensure related items are fresh before returning
        return cls.get_content_post(post_id=content_post.id, user=content_post.user)

    @classmethod
    def delete_content_post(cls, content_post: ContentPost) -> None:
        """
        Deletes a content post entirely.
        Only allowed if ALL platform entries are still PENDING or SCHEDULED.
        """
        from content.services.posting_service import PostingService

        for entry in content_post.platform_entries.all():
            if entry.status not in [PostStatus.PENDING, PostStatus.SCHEDULED]:
                raise ValueError(
                    f"Cannot delete post because platform '{entry.platform}' is in status '{entry.status}'. "
                    "Only fully pending or scheduled posts can be deleted."
                )

        # Cleanup R2 media files before deleting the post to prevent orphaned files
        PostingService.cleanup_r2_media(content_post)

        # Delete the post (this cascades to ContentMedia and ContentPostPlatform)
        content_post.delete()
