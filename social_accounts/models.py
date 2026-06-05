from datetime import timedelta
from django.db import models
from django.conf import settings
from django.db.models import UniqueConstraint
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from integrations.providers.instagram_service import InstagramService
from integrations.providers.youtube_service import YoutubeService
from social_accounts.utils.encryption import decrypt_text, encrypt_text
from post_reach_backend.models import UUIDTimestampedModel

# Create your models here.
class Brand(UUIDTimestampedModel):
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

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brands'
    )
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    industry = models.CharField(
        max_length=100,
        choices=IndustryChoices.choices,
        blank=True,
        null=True,
    )
    posting_frequency = models.CharField(max_length=100, blank=True, null=True)
    primary_platform = models.CharField(
        max_length=100,
        choices=PlatformChoices.choices,
        blank=True,
        null=True,
    )
    team_size = models.CharField(
        max_length=100,
        choices=TeamSizeChoices.choices,
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "name"],
                name="unique_user_brand_name",
            ),
            UniqueConstraint(
                fields=["user", "is_default"],
                name="unique_user_default_brand",
            )
        ]

class SocialAccount(UUIDTimestampedModel):
    PROVIDER_CHOICES = [
        ("youtube", "YouTube"),
        ("instagram", "Instagram"),
        ("tiktok", "TikTok"),
        ("facebook", "Facebook"),
    ]
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='social_accounts')
    account_type = models.CharField(max_length=50, choices=PROVIDER_CHOICES)

    _access_token = models.TextField()
    _refresh_token = models.TextField(blank=True, null=True)

    expires_at = models.DateTimeField()
    scope = models.TextField(blank=True, null=True)
    token_type = models.CharField(max_length=50, default="Bearer")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["brand", "account_type"],
                name="unique_brand_social_account",
            )
        ]

    @property
    def access_token(self):
        return decrypt_text(self._access_token)

    @access_token.setter
    def access_token(self, value):
        self._access_token = encrypt_text(value)

    @property
    def refresh_token(self):
        if self._refresh_token:
            return decrypt_text(self._refresh_token)
        return None

    @refresh_token.setter
    def refresh_token(self, value):
        self._refresh_token = encrypt_text(value) if value else None

    @property
    def scopes_list(self):
        return self.scope.split() if self.scope else []

    def is_token_expired(self):
        return self.expires_at and self.expires_at <= timezone.now()

    def get_access_token(self):
        """
        This method returns None if token is expired and unable to refresh the token
        therefore you should shseck if .get_access_token() is valid before proceeding to use the access token
        peace 👌
        """
        if self.is_token_expired():
            if not self.refresh_access_token():
                return None

        return self.access_token

    def refresh_access_token(self):
        """
        Refreshes the access token if it is expired or about to expire.
        Returns the new access token or None if refresh fails.
        """
        try:
            if self.account_type == "youtube":
                response = YoutubeService.refresh_access_token(self.refresh_token)
                self.access_token = response["access_token"]
                self.refresh_token = response["refresh_token"]
                self.expires_at = response["expires_in"]
                self.save()
                return True

            elif self.account_type == "instagram":
                response = InstagramService.refresh_access_token(self.access_token)
                self.access_token = response["access_token"]
                self.expires_at = timezone.now() + timedelta(seconds=response["expires_in"])
                self.save()
                return True

            # Facebook and others without refresh logic
            return False

        except Exception:
            return False

    def __str__(self):
        return f"{self.user.email} - {self.account_type}"
