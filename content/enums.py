from django.db import models


class PostStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SCHEDULED = "scheduled", "Scheduled"
    UPLOADING = "uploading", "Uploading to Platform"
    PROCESSING = "processing", "Processing on Platform"
    POSTED = "posted", "Posted Successfully"
    FAILED = "failed", "Posting Failed"


class FileTypeChoice(models.TextChoices):
    IMAGE = "image", "Image"
    VIDEO = "video", "Video"


class PhotoPlatformOptions(models.TextChoices):
    """Platforms that support photo posts (YouTube does not support photos)."""

    INSTAGRAM = "instagram", "Instagram"
    FACEBOOK = "facebook", "Facebook"
    TIKTOK = "tiktok", "TikTok"
    LINKEDIN = "linkedin", "LinkedIn"
    TWITTER = "twitter", "Twitter"


class TextPlatformOptions(models.TextChoices):
    """Platforms that support text-only posts (YouTube, Instagram, TikTok do not support text-only)."""

    FACEBOOK = "facebook", "Facebook"
    LINKEDIN = "linkedin", "LinkedIn"
    TWITTER = "twitter", "Twitter"
