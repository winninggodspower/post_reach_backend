from django.conf import settings
from django.db import models

from content.enums import PostStatus
from post_reach_backend.models import UUIDTimestampedModel
from social_accounts.enums import PlatformChoices
from users.models import Brand


class ContentPost(UUIDTimestampedModel):
    """
    Represents a single video upload that can be posted to one or more platforms.
    Platform-specific status is tracked via ContentPostPlatform entries.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_posts",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="content_posts",
    )

    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    # R2 object key for the uploaded video (shared across all platforms)
    video_r2_key = models.CharField(max_length=512)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["brand"]),
        ]

    def __str__(self):
        platforms = ", ".join(
            self.platform_entries.values_list("platform", flat=True)
        )
        return f"{self.brand.name} → [{platforms}]"


class ContentPostPlatform(UUIDTimestampedModel):
    """
    Tracks the publishing status for a ContentPost on a single platform.
    One ContentPost has one ContentPostPlatform per target platform.
    """

    content_post = models.ForeignKey(
        ContentPost,
        on_delete=models.CASCADE,
        related_name="platform_entries",
    )
    platform = models.CharField(
        max_length=50,
        choices=PlatformChoices.choices,
    )

    status = models.CharField(
        max_length=20,
        choices=PostStatus.choices,
        default=PostStatus.PENDING,
    )
    platform_post_id = models.CharField(
        max_length=255, blank=True, default="",
        help_text="The post/video ID returned by the platform API.",
    )
    error_message = models.TextField(
        blank=True, default="",
        help_text="Error details if this platform post failed.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["content_post", "platform"],
                name="unique_content_post_platform",
            ),
        ]
        ordering = ["platform"]

    def __str__(self):
        return f"{self.content_post} → {self.platform} ({self.status})"