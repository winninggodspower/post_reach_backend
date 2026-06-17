from datetime import timedelta

from django.utils import timezone

from integrations.providers.base import SocialAccountService
from social_accounts.models import SocialAccount
from integrations.providers.facebook_service import FacebookService
from integrations.providers.instagram_service import InstagramService
from integrations.providers.linkedin_service import LinkedinService
from integrations.providers.tiktok_service import TiktokService
from integrations.providers.youtube_service import YoutubeService
from utils.custom_logger import log_exceptions


class SocialAccountConnectionService:
    @classmethod
    @log_exceptions()
    def _save_account(cls, *, brand, platform, defaults):
        return SocialAccount.objects.update_or_create(
            brand=brand,
            platform=platform,
            defaults=defaults,
        )

    @classmethod
    @log_exceptions()
    def connect_youtube(cls, *, user, brand, auth_code):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        credentials, missing_scopes = YoutubeService.exchange_code_for_token(
            auth_code=auth_code,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        # Fetch channel info (account name and external ID)
        channel_info = YoutubeService._fetch_channel_info(credentials)

        return cls._save_account(
            brand=resolved_brand,
            platform="youtube",
            defaults={
                "account_name": channel_info["account_name"],
                "external_id": channel_info["external_id"],
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expires_at": credentials.expiry,
                "scope": " ".join(credentials.scopes),
            },
        )

    @classmethod
    @log_exceptions()
    def connect_facebook(cls, *, user, brand, code, redirect_uri, page_id=""):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        long_lived_token, expires_in = FacebookService.exchange_code_for_token(
            code, redirect_uri
        )

        # Fetch Facebook pages and select the target page
        pages = FacebookService.get_facebook_pages(long_lived_token)
        if page_id:
            page = next((p for p in pages if p["id"] == page_id), None)
            if not page:
                raise ValueError(f"Facebook page with ID '{page_id}' not found in your account")
        else:
            page = pages[0]  # Default to the first page

        return cls._save_account(
            brand=resolved_brand,
            platform="facebook",
            defaults={
                "account_name": page["name"],
                "external_id": page["id"],
                "access_token": page["access_token"],
                "token_expires_at": timezone.now() + timedelta(seconds=expires_in),
            },
        )

    @classmethod
    @log_exceptions()
    def connect_instagram(cls, *, user, brand, auth_code, redirect_uri):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        credentials, missing_scopes = InstagramService.exchange_code_for_token(
            auth_code=auth_code,
            redirect_uri=redirect_uri,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        return cls._save_account(
            brand=resolved_brand,
            platform="instagram",
            defaults={
                "access_token": credentials["access_token"],
                "token_expires_at": timezone.now() + timedelta(seconds=credentials["expires_in"]),
            },
        )

    @classmethod
    @log_exceptions()
    def connect_tiktok(cls, *, user, brand, code, redirect_uri):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        token_data = TiktokService.exchange_code_for_token(code, user.id)

        access_token = token_data["access_token"]

        # Fetch TikTok user info (account name and external ID)
        user_info = TiktokService.fetch_user_info(access_token)

        return cls._save_account(
            brand=resolved_brand,
            platform="tiktok",
            defaults={
                "account_name": user_info["account_name"],
                "external_id": user_info["external_id"],
                "access_token": access_token,
                "refresh_token": token_data.get("refresh_token"),
                "token_expires_at": timezone.now() + timedelta(seconds=token_data["expires_in"]),
                "scope": token_data.get("scope", ""),
            },
        )

    @classmethod
    @log_exceptions()
    def connect_linkedin(cls, *, user, brand, code, redirect_uri):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        token_data = LinkedinService.exchange_code_for_token(code, redirect_uri)

        access_token = token_data["access_token"]

        # Fetch LinkedIn user info (account name and external ID)
        user_info = LinkedinService.fetch_user_info(access_token)

        return cls._save_account(
            brand=resolved_brand,
            platform="linkedin",
            defaults={
                "account_name": user_info["account_name"],
                "external_id": user_info["external_id"],
                "access_token": access_token,
                "token_expires_at": timezone.now() + timedelta(seconds=token_data["expires_in"]),
                "scope": token_data.get("scope", ""),
            },
        )
