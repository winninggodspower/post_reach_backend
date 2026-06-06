from django.db import models


class PlatformChoices(models.TextChoices):
    YOUTUBE = "youtube", "YouTube"
    INSTAGRAM = "instagram", "Instagram"
    TIKTOK = "tiktok", "TikTok"
    FACEBOOK = "facebook", "Facebook"
    LINKEDIN = "linkedin", "LinkedIn"
