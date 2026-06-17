"""
Service layer for ContentPost model queries.
Encapsulates all direct ContentPost model access so views and other services
never import from content.models directly.
"""

from uuid import UUID

from django.db.models import Prefetch

from content.models import ContentMedia, ContentPost, ContentPostPlatform
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
    def get_media_items(cls, content_post: ContentPost, file_type: str = "image"):
        """
        Get media items for a post filtered by file_type, ordered by position.
        """
        return content_post.media_items.filter(file_type=file_type).order_by("order")

    @classmethod
    def has_pending_entries(cls, content_post: ContentPost) -> bool:
        """
        Check if any platform entry for this post is still pending or uploading.
        """
        from content.enums import PostStatus

        return content_post.platform_entries.filter(
            status__in=[PostStatus.PENDING, PostStatus.UPLOADING]
        ).exists()