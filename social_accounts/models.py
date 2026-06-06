from datetime import timedelta
from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone

from integrations.providers.instagram_service import InstagramService
from integrations.providers.youtube_service import YoutubeService
from social_accounts.enums import PlatformChoices
from social_accounts.utils.encryption import decrypt_text, encrypt_text
from post_reach_backend.models import UUIDTimestampedModel
from users.models import Brand

# Create your models here.

class SocialAccount(UUIDTimestampedModel):
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='social_accounts')
    platform = models.CharField(max_length=50, choices=PlatformChoices.choices)

    account_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The username or page name associated with the social account (e.g., @username for Instagram or page name for Facebook)."
    )
    external_id = models.CharField(
        max_length=255,
        help_text="The unique identifier for the social account on the platform."
    )

    _access_token = models.TextField()
    _refresh_token = models.TextField(blank=True, null=True)
    token_expires_at = models.DateTimeField()
    scope = models.TextField(blank=True, null=True)
    token_type = models.CharField(max_length=50, default="Bearer")

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["brand", "platform"],
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
        return self.token_expires_at  and self.token_expires_at  <= timezone.now()

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
            if self.platform == PlatformChoices.YOUTUBE:
                response = YoutubeService.refresh_access_token(self.refresh_token)
                self.access_token = response["access_token"]
                self.refresh_token = response["refresh_token"]
                self.token_expires_at  = response["expires_in"]
                self.save()
                return True

            elif self.platform == PlatformChoices.INSTAGRAM:
                response = InstagramService.refresh_access_token(self.access_token)
                self.access_token = response["access_token"]
                self.token_expires_at  = timezone.now() + timedelta(seconds=response["expires_in"])
                self.save()
                return True

            # Facebook, LinkedIn, TikTok and others without refresh logic
            return False

        except Exception:
            return False

    def __str__(self):
        return f"{self.brand.name} - {self.platform}"
