"""
Selector layer for ContentPost queries.

Encapsulates all pure-read database access and queries for ContentPost,
keeping query logic decoupled from mutation/business logic services.
All public methods are classmethods or staticmethods and have zero side-effects.
"""

from typing import Optional
from uuid import UUID

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from content.enums import FileTypeChoice, PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from users.models import Brand, User


class ContentPostSelector:
    """Pure query / read selector for ContentPost records."""

    @classmethod
    def get_content_post(cls, post_id: UUID | str, user: User) -> ContentPost:
        """
        Retrieve a single ContentPost by ID, ensuring it belongs to the given user.
        Prefetches media_items and platform_entries.

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
    def get_content_post_by_id(cls, post_id: UUID | str) -> ContentPost:
        """
        Retrieve a ContentPost by ID with related user, brand, and platform_entries.

        :raises ContentPost.DoesNotExist: If not found.
        :return: The ContentPost instance.
        """
        return (
            ContentPost.objects.select_related("user", "brand")
            .prefetch_related("platform_entries")
            .get(id=post_id)
        )

    @classmethod
    def get_scheduled_posts(
        cls,
        *,
        brand: Brand,
        platform: str | None = None,
        content_type: str | None = None,
        limit: int | None = None,
    ) -> QuerySet[ContentPost]:
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
    def get_calendar_posts(
        cls,
        *,
        brand: Brand,
        start_date=None,
        end_date=None,
    ) -> QuerySet[ContentPost]:
        """
        Retrieves calendar posts for a brand within an optional date range.
        Prefetches platform_entries and media_items.
        """
        posts = ContentPost.objects.filter(brand=brand).prefetch_related(
            "platform_entries", "media_items"
        )

        if start_date:
            posts = posts.filter(
                Q(scheduled_at__date__gte=start_date)
                | Q(scheduled_at__isnull=True, created_at__date__gte=start_date)
            )

        if end_date:
            posts = posts.filter(
                Q(scheduled_at__date__lte=end_date)
                | Q(scheduled_at__isnull=True, created_at__date__lte=end_date)
            )

        return posts.order_by("scheduled_at", "created_at")

    @classmethod
    def get_media_items(
        cls,
        content_post: ContentPost,
        file_type: str = FileTypeChoice.IMAGE,
    ) -> QuerySet[ContentMedia]:
        """
        Get media items for a post filtered by file_type, ordered by position.
        """
        return content_post.media_items.filter(file_type=file_type).order_by("order")

    @classmethod
    def has_pending_entries(cls, content_post: ContentPost) -> bool:
        """
        Check if any platform entry for this post is still pending, scheduled,
        uploading, or processing.
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
    def get_expired_failed_posts(cls, cutoff_date) -> QuerySet[ContentPost]:
        """
        Retrieves distinct posts where:
        - At least one platform entry failed at or before cutoff_date
        - Either post has no scheduled time, or scheduled_at is at or before cutoff_date
        - No platform entry is still pending, scheduled, uploading, or processing
        - No platform entry was updated after cutoff_date (e.g. recently retried)
        """
        return (
            ContentPost.objects.filter(
                platform_entries__status=PostStatus.FAILED,
                platform_entries__updated_at__lte=cutoff_date,
            )
            .filter(Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=cutoff_date))
            .exclude(
                platform_entries__status__in=[
                    PostStatus.PENDING,
                    PostStatus.SCHEDULED,
                    PostStatus.UPLOADING,
                    PostStatus.PROCESSING,
                ]
            )
            .exclude(platform_entries__updated_at__gt=cutoff_date)
            .distinct()
            .prefetch_related("media_items", "platform_entries")
        )
