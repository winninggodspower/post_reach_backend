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
    JUST_ME = "1", "1"
    TWO_TO_FIVE = "2-5", "2-5"
    SIX_TO_TWENTY = "6-20", "6-20"
    TWENTY_ONE_TO_FIFTY = "21-50", "21-50"
    FIFTY_ONE_PLUS = "51+", "51+"
