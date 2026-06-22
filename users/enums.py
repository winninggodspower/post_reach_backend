from django.db import models


class IndustryChoices(models.TextChoices):
    TECHNOLOGY = "technology", "Technology"
    MARKETING = "marketing", "Marketing"
    ECOMMERCE = "ecommerce", "Ecommerce"
    REAL_ESTATE = "real_estate", "Real Estate"
    HEALTHCARE = "healthcare", "Healthcare"
    EDUCATION = "education", "Education"
    FINANCE = "finance", "Finance"
    OTHER = "other", "Other"


class PlatformChoices(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    LINKEDIN = "linkedin", "LinkedIn"
    TIKTOK = "tiktok", "TikTok"
    FACEBOOK = "facebook", "Facebook"
    X = "x", "X"
    YOUTUBE = "youtube", "YouTube"


class TeamSizeChoices(models.TextChoices):
    JUST_ME = "just_me", "Just Me"
    SMALL_TEAM = "small_team", "Small Team"
    MEDIUM_TEAM = "medium_team", "Medium Team"
    LARGE_TEAM = "large_team", "Large Team"
