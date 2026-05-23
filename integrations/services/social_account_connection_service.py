from datetime import timedelta

from django.utils import timezone

from social_accounts.models import SocialAccount
from social_accounts.services.facebook_service import FacebookService
from social_accounts.services.instagram_service import InstagramService
from social_accounts.services.linkedin_service import LinkedinService
from social_accounts.services.tiktok_service import TiktokService
from social_accounts.services.youtube_service import YoutubeService


class SocialAccountConnectionService:
    @staticmethod
    def _ensure_brand_owned_by_user(user, brand):
        if brand.user_id != user.id:
            raise PermissionError("You do not have permission to access this brand.")

    @classmethod
    def _save_account(cls, *, brand, account_type, defaults):
        return SocialAccount.objects.update_or_create(
            brand=brand,
            account_type=account_type,
            defaults=defaults,
        )

    @classmethod
    def connect_youtube(cls, *, user, brand, auth_code, redirect_uri):
        cls._ensure_brand_owned_by_user(user, brand)

        credentials, missing_scopes = YoutubeService.exchange_code_for_token(
            auth_code=auth_code,
            google_auth_redirect_uri=redirect_uri,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        return cls._save_account(
            brand=brand,
            account_type="youtube",
            defaults={
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "expires_at": credentials.expiry,
                "scope": " ".join(credentials.scopes),
            },
        )

    @classmethod
    def connect_facebook(cls, *, user, brand, short_lived_access_token):
        cls._ensure_brand_owned_by_user(user, brand)

        long_lived_token, expires_in = FacebookService.exchange_short_lived_token(
            short_lived_access_token
        )

        return cls._save_account(
            brand=brand,
            account_type="facebook",
            defaults={
                "access_token": long_lived_token,
                "expires_at": timezone.now() + timedelta(seconds=expires_in),
            },
        )

    @classmethod
    def connect_instagram(cls, *, user, brand, auth_code, redirect_uri):
        cls._ensure_brand_owned_by_user(user, brand)

        credentials, missing_scopes = InstagramService.exchange_code_for_token(
            auth_code=auth_code,
            redirect_uri=redirect_uri,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        return cls._save_account(
            brand=brand,
            account_type="instagram",
            defaults={
                "access_token": credentials["access_token"],
                "expires_at": timezone.now() + timedelta(seconds=credentials["expires_in"]),
            },
        )

    @classmethod
    def connect_tiktok(cls, *, user, brand, code):
        cls._ensure_brand_owned_by_user(user, brand)

        token_data = TiktokService.exchange_code_for_token(code)

        return cls._save_account(
            brand=brand,
            account_type="tiktok",
            defaults={
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": timezone.now() + timedelta(seconds=token_data["expires_in"]),
                "scope": token_data.get("scope", ""),
            },
        )

    @classmethod
    def connect_linkedin(cls, *, user, brand, code, redirect_uri):
        cls._ensure_brand_owned_by_user(user, brand)

        token_data = LinkedinService.exchange_code_for_token(code, redirect_uri)

        return cls._save_account(
            brand=brand,
            account_type="linkedin",
            defaults={
                "access_token": token_data["access_token"],
                "expires_at": timezone.now() + timedelta(seconds=token_data["expires_in"]),
                "scope": token_data.get("scope", ""),
            },
        )