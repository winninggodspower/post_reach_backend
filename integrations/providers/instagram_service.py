import requests
from django.conf import settings

from integrations.providers.base import SocialAccountService


class InstagramService(SocialAccountService):
    APP_ID = settings.INSTAGRAM_APP_ID
    APP_SECRET = settings.INSTAGRAM_APP_SECRET
    BASE_URL = "https://graph.instagram.com"

    REQUIRED_PERMISSIONS = {
        "public_profile",
        "instagram_business_content_publish",
    }

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
        url = "https://api.instagram.com/oauth/access_token"
        data = {
            "client_id": cls.APP_ID,
            "client_secret": cls.APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": auth_code,
        }

        response = requests.post(url, data=data)
        response_data = response.json()

        if "access_token" not in response_data:
            raise ValueError(response_data.get("error_message", "Could not get short-lived token"))

        return response_data

    @classmethod
    def _get_long_lived_token(cls, short_lived_token):
        url = f"{cls.BASE_URL}/access_token"
        params = {
            "grant_type": "ig_exchange_token",
            "client_secret": cls.APP_SECRET,
            "access_token": short_lived_token,
        }

        response = requests.get(url, params=params)
        response_data = response.json()

        if "access_token" not in response_data:
            raise ValueError(response_data.get("error", {}).get("message", "Could not get long-lived token"))

        return response_data

    @classmethod
    def refresh_access_token(cls, long_lived_token: str):
        url = f"{cls.BASE_URL}/refresh_access_token"

        response = requests.get(
            url,
            params={
                "grant_type": "ig_refresh_token",
                "access_token": long_lived_token,
            },
        )
        response_data = response.json()

        if "access_token" not in response_data:
            raise ValueError(response_data.get("error", {}).get("message", "Unknown error"))

        return {
            "access_token": response_data["access_token"],
            "refresh_token": None,
            "expires_in": response_data["expires_in"],
        }
