from django.db import models


class PostStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    UPLOADING = "uploading", "Uploading to Platform"
    POSTED = "posted", "Posted Successfully"
    FAILED = "failed", "Posting Failed"