from django.conf import settings

from integrations.providers.base import SocialAccountService
from utils.http import APIError
from utils.custom_logger import CustomLogger

class LinkedinService(SocialAccountService):
    CLIENT_ID = settings.LINKEDIN_CLIENT_ID
    CLIENT_SECRET = settings.LINKEDIN_CLIENT_SECRET
    BASE_URL = "https://www.linkedin.com/oauth/v2"

    @classmethod
    def exchange_code_for_token(cls, code, redirect_uri):
        try:
            response_data = cls().post(
                "/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": cls.CLIENT_ID,
                    "client_secret": cls.CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except APIError as e:
            CustomLogger.exception("LinkedIn token exchange failed", extra={"operation": "exchange_code_for_token", "redirect_uri": redirect_uri})
            raise ValueError(f"LinkedIn Auth Error: {e}") from e
        if "access_token" not in response_data:
            error_message = (
                response_data.get("error_description")
                or response_data.get("error")
                or "LinkedIn token exchange failed"
            )
            raise ValueError(f"LinkedIn Auth Error: {error_message}")
        return response_data

    @classmethod
    def refresh_access_token(cls, refresh_token):
        return None
