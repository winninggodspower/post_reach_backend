import uuid

from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from social_accounts.utils.cache_keys import facebook_oauth_state
from utils.http import APIError
from utils.custom_logger import CustomLogger

OAUTH_STATE_TTL = 600  # 10 minutes


class FacebookService(SocialAccountService):
    CLIENT_ID = settings.FACEBOOK_CLIENT_ID
    CLIENT_SECRET = settings.FACEBOOK_CLIENT_SECRET
    BASE_URL = "https://graph.facebook.com/v18.0"
    redirect_uri = settings.REDIRECT_URI["facebook"]

    REQUIRED_PERMISSIONS = {
        "public_profile",
        "publish_video",
    }

    SCOPES = [
        "public_profile",
        "publish_video",
    ]

    @classmethod
    def generate_auth_url(cls, user_id):
        """
        Generates a Facebook OAuth authorization URL with CSRF state protection.
        Stores the state in cache for later verification.
        The redirect URI is resolved from settings.REDIRECT_URI["facebook"].
        """
        redirect_uri = cls.redirect_uri
        state = str(uuid.uuid4())
        cache.set(facebook_oauth_state(user_id), state, OAUTH_STATE_TTL)

        params = {
            "client_id": cls.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(cls.SCOPES),
            "response_type": "code",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://www.facebook.com/v18.0/dialog/oauth?{query_string}"

    @classmethod
    def refresh_access_token(self, refresh_token):
        return None

    @classmethod
    def exchange_short_lived_token(cls, short_lived_token):
        try:
            is_valid, missing_permissions = cls.verify_granted_scope(short_lived_token)
        except APIError as e:
            CustomLogger.exception("Facebook permission verification failed", extra={"operation": "verify_granted_scope"})
            raise ValueError(str(e)) from e

        if not is_valid:
            raise ValueError(
                f"Missing required Facebook permissions: {', '.join(missing_permissions)}"
            )

        try:
            data = cls().get(
                "/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": cls.CLIENT_ID,
                    "client_secret": cls.CLIENT_SECRET,
                    "fb_exchange_token": short_lived_token,
                },
            )
        except APIError as e:
            CustomLogger.exception("Facebook token exchange failed", extra={"operation": "exchange_short_lived_token"})
            raise ValueError(str(e)) from e

        if "access_token" not in data:
            raise ValueError(data.get("error", {}).get("message", "Unknown error"))

        return data["access_token"], int(data["expires_in"])

    @classmethod
    def verify_granted_scope(cls, access_token):
        data = cls().get(
            "/me/permissions",
            params={"access_token": access_token},
        )

        if "data" not in data:
            error_msg = data.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", "Failed to verify permissions")
            else:
                error_msg = str(error_msg)
            raise ValueError(error_msg)

        granted_permissions = {
            perm["permission"] for perm in data["data"] if perm["status"] == "granted"
        }

        missing_permissions = cls.REQUIRED_PERMISSIONS - granted_permissions

        return (not bool(missing_permissions), missing_permissions)

    @classmethod
    def get_facebook_pages(cls, access_token):
        pass
