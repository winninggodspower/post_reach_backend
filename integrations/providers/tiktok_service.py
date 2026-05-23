from django.conf import settings

from integrations.providers.base import SocialAccountService
from utils.http import APIError


class TiktokService(SocialAccountService):
    CLIENT_KEY = settings.TIKTOK_CLIENT_KEY
    CLIENT_SECRET = settings.TIKTOK_CLIENT_SECRET
    BASE_URL = "https://open-api.tiktok.com"

    @classmethod
    def exchange_code_for_token(cls, code):
        try:
            response = cls().post(
                "/oauth/access_token/",
                data={
                    "client_key": cls.CLIENT_KEY,
                    "client_secret": cls.CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
        except APIError as e:
            raise ValueError(str(e)) from e
        if not response:
            raise ValueError("Error while fetching access token from TikTok")

        return response

    @classmethod
    def refresh_access_token(cls, refresh_token):
        try:
            response = cls().post(
                "/oauth/refresh_token/",
                data={
                    "client_key": cls.CLIENT_KEY,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        except APIError as e:
            raise ValueError(str(e)) from e
        if not response:
            raise ValueError("Error while refreshing access token from TikTok")

        return response
