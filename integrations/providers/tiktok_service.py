import requests
from django.conf import settings

from integrations.providers.base import SocialAccountService


class TiktokService(SocialAccountService):
    CLIENT_KEY = settings.TIKTOK_CLIENT_KEY
    CLIENT_SECRET = settings.TIKTOK_CLIENT_SECRET

    @classmethod
    def exchange_code_for_token(cls, code):
        url = "https://open-api.tiktok.com/oauth/access_token/"
        data = {
            "client_key": cls.CLIENT_KEY,
            "client_secret": cls.CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }

        response = requests.post(url, data=data)
        if response.status_code != 200:
            raise ValueError("Error while fetching access token from TikTok")

        return response.json()

    @classmethod
    def refresh_access_token(cls, refresh_token):
        url = "https://open-api.tiktok.com/oauth/refresh_token/"
        data = {
            "client_key": cls.CLIENT_KEY,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        response = requests.post(url, data=data)
        if response.status_code != 200:
            raise ValueError("Error while refreshing access token from TikTok")

        return response.json()
