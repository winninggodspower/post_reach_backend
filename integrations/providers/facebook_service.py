from django.conf import settings

from integrations.providers.base import SocialAccountService
from utils.http import APIError
from utils.custom_logger import CustomLogger


class FacebookService(SocialAccountService):
    CLIENT_ID = settings.FACEBOOK_CLIENT_ID
    CLIENT_SECRET = settings.FACEBOOK_CLIENT_SECRET
    BASE_URL = "https://graph.facebook.com/v18.0"

    REQUIRED_PERMISSIONS = {
        "public_profile",
        "publish_video",
    }

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
            raise ValueError(
                data.get("error", {}).get("message", "Failed to verify permissions")
            )

        granted_permissions = {
            perm["permission"] for perm in data["data"] if perm["status"] == "granted"
        }

        missing_permissions = cls.REQUIRED_PERMISSIONS - granted_permissions

        return (not bool(missing_permissions), missing_permissions)

    @classmethod
    def get_facebook_pages(cls, access_token):
        pass
