import requests
from django.conf import settings

from integrations.providers.base import SocialAccountService


class LinkedinService(SocialAccountService):
    CLIENT_ID = settings.LINKEDIN_CLIENT_ID
    CLIENT_SECRET = settings.LINKEDIN_CLIENT_SECRET
    BASE_URL = "https://www.linkedin.com/oauth/v2"

    @classmethod
    def exchange_code_for_token(cls, code, redirect_uri):
        url = cls.BASE_URL + "/accessToken"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cls.CLIENT_ID,
            "client_secret": cls.CLIENT_SECRET,
            "redirect_uri": redirect_uri,
        }
        response = requests.post(url, headers=headers, data=data)
        response_data = response.json()
        if response.status_code != 200 or "access_token" not in response_data:
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
