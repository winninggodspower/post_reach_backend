"""
Service layer for ContentPost model queries.
Encapsulates all direct ContentPost model access so views and other services
never import from content.models directly.
"""

from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch

from content.enums import FileTypeChoice, PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from content.tasks import publish_platform_entry
from social_accounts.services.social_account_validation_service import (
    SocialAccountValidationService,
)
from users.models import User


class ContentPostService:
    """
    Stateless service for querying ContentPost records.
    All public methods are classmethods.
    """

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
            status__in=[PostStatus.PENDING, PostStatus.UPLOADING]
        ).exists()

    @classmethod
    def update_content_post(cls, content_post: ContentPost, validated_data: dict) -> ContentPost:
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
            content_post.scheduled_at = validated_data["scheduled_at"]
            save_post = True

        if save_post:
            content_post.save()

        with transaction.atomic():
            if "platforms" in validated_data:
                new_platform_set = set(validated_data["platforms"])
                existing_platform_set = {entry.platform for entry in content_post.platform_entries.all()}
                
                platforms_to_add = new_platform_set - existing_platform_set
                platforms_to_remove = existing_platform_set - new_platform_set

                if platforms_to_add:
                    SocialAccountValidationService.ensure_platforms_connected(content_post.brand, list(platforms_to_add))
                    
                    initial_status = PostStatus.SCHEDULED if content_post.scheduled_at else PostStatus.PENDING
                    platform_settings = validated_data.get("platform_settings", {})
                    new_entries = []
                    
                    for platform in platforms_to_add:
                        plat_settings = platform_settings.get(platform, {})
                        if platform == "youtube":
                            title = plat_settings.get("title", "")
                            plat_caption = plat_settings.get("description", plat_settings.get("caption", content_post.caption))
                        else:
                            title = ""
                            plat_caption = plat_settings.get("caption", content_post.caption)

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
                        newly_created = ContentPostPlatform.objects.filter(content_post=content_post, platform__in=platforms_to_add)
                        for entry in newly_created:
                            def dispatch_task(e_id=str(entry.id), c_type=content_post.content_type):
                                publish_platform_entry.delay(e_id, content_type=c_type)
                            transaction.on_commit(dispatch_task)

                if platforms_to_remove:
                    content_post.platform_entries.filter(platform__in=platforms_to_remove).delete()

            # Refresh the platforms so we can update settings safely
            platform_settings = validated_data.get("platform_settings")
            if platform_settings:
                # We need to query again to ensure we have the latest entries if they were modified
                current_entries = ContentPostPlatform.objects.filter(content_post=content_post)
                for entry in current_entries:
                    if entry.platform in platform_settings:
                        current_settings = entry.settings or {}
                        current_settings.update(platform_settings[entry.platform])
                        entry.settings = current_settings
                        entry.save()

        # Re-fetch the content_post from DB to ensure related items are fresh before returning
        return cls.get_content_post(post_id=content_post.id, user=content_post.user)
