import uuid

from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from social_accounts.utils.cache_keys import instagram_oauth_state
from utils.http import APIError
from utils.custom_logger import CustomLogger

OAUTH_STATE_TTL = 600  # 10 minutes


class InstagramService(SocialAccountService):
    APP_ID = settings.INSTAGRAM_APP_ID
    APP_SECRET = settings.INSTAGRAM_APP_SECRET
    BASE_URL = "https://graph.instagram.com"
    redirect_uri = settings.REDIRECT_URI["instagram"]

    REQUIRED_PERMISSIONS = {
        "instagram_business_basic",
        "instagram_business_content_publish",
    }

    @classmethod
    def generate_auth_url(cls, user_id):
        """
        Generates an Instagram OAuth authorization URL with CSRF state protection.
        Stores the state in cache for later verification.
        The redirect URI is resolved from settings.REDIRECT_URI["instagram"].
        """
        redirect_uri = cls.redirect_uri
        state = str(uuid.uuid4())
        cache.set(instagram_oauth_state(user_id), state, OAUTH_STATE_TTL)

        params = {
            "client_id": cls.APP_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(cls.REQUIRED_PERMISSIONS),
            "response_type": "code",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://api.instagram.com/oauth/authorize?{query_string}"

    @classmethod
    def exchange_code_for_token(cls, auth_code, redirect_uri):
        short_lived_token_data = cls._get_short_lived_token(auth_code, redirect_uri)
        long_lived_token_data = cls._get_long_lived_token(short_lived_token_data["access_token"])

        return {
            "access_token": long_lived_token_data["access_token"],
            "expires_in": long_lived_token_data["expires_in"],
            "user_id": short_lived_token_data["user_id"],
        }, []

    @classmethod
    def _get_short_lived_token(cls, auth_code, redirect_uri):
        try:
            response_data = cls().post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": cls.APP_ID,
                    "client_secret": cls.APP_SECRET,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": auth_code,
                },
            )
        except APIError as e:
            CustomLogger.exception("Instagram short-lived token exchange failed", extra={"operation": "_get_short_lived_token"})
            raise ValueError(str(e)) from e

        if "access_token" not in response_data:
            raise ValueError(
                response_data.get("error_message", "Could not get short-lived token")
            )

        return response_data

    @classmethod
    def _get_long_lived_token(cls, short_lived_token):
        try:
            response_data = cls().get(
                "/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": cls.APP_SECRET,
                    "access_token": short_lived_token,
                },
            )
        except APIError as e:
            CustomLogger.exception("Instagram long-lived token exchange failed", extra={"operation": "_get_long_lived_token"})
            raise ValueError(str(e)) from e

        if "access_token" not in response_data:
            raise ValueError(
                response_data.get("error", {}).get("message", "Could not get long-lived token")
            )

        return response_data

    @classmethod
    def refresh_access_token(cls, long_lived_token: str):
        try:
            response_data = cls().get(
                "/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": long_lived_token,
                },
            )
        except APIError as e:
            CustomLogger.exception("Instagram access token refresh failed", extra={"operation": "refresh_access_token"})
            raise ValueError(str(e)) from e

        if "access_token" not in response_data:
            raise ValueError(
                response_data.get("error", {}).get("message", "Unknown error")
            )

        return {
            "access_token": response_data["access_token"],
            "refresh_token": None,
            "expires_in": response_data["expires_in"],
        }
