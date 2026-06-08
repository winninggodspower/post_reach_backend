import uuid

from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from social_accounts.utils.cache_keys import linkedin_oauth_state
from utils.http import APIError
from utils.custom_logger import CustomLogger

OAUTH_STATE_TTL = 600  # 10 minutes


class LinkedinService(SocialAccountService):
    CLIENT_ID = settings.LINKEDIN_CLIENT_ID
    CLIENT_SECRET = settings.LINKEDIN_CLIENT_SECRET
    BASE_URL = "https://www.linkedin.com/oauth/v2"
    API_BASE_URL = "https://api.linkedin.com/v2"
    redirect_uri = settings.REDIRECT_URI["linkedin"]

    REQUIRED_SCOPES = {
        "openid",
        "profile",
        "email",
        "w_member_social",
    }

    @classmethod
    def generate_auth_url(cls, user_id):
        """
        Generates a LinkedIn OAuth authorization URL with CSRF state protection.
        Stores the state in cache for later verification.
        The redirect URI is resolved from settings.REDIRECT_URI["linkedin"].
        """
        redirect_uri = cls.redirect_uri
        state = str(uuid.uuid4())
        cache.set(linkedin_oauth_state(user_id), state, OAUTH_STATE_TTL)

        params = {
            "client_id": cls.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(cls.REQUIRED_SCOPES),
            "response_type": "code",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{cls.BASE_URL}/authorization?{query_string}"

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
    def fetch_user_info(cls, access_token):
        """
        Fetches the LinkedIn user profile info using the access token.
        Returns a dict with 'account_name' and 'external_id'.
        Uses the OpenID Connect userinfo endpoint with Bearer token auth.
        """
        try:
            data = cls().get(
                f"{cls.API_BASE_URL}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except APIError as e:
            CustomLogger.exception("Failed to fetch LinkedIn user info", extra={"operation": "fetch_user_info"})
            raise ValueError(f"Failed to fetch LinkedIn user info: {str(e)}") from e

        external_id = data.get("sub")
        if not external_id:
            raise ValueError("Failed to retrieve LinkedIn user ID")

        # Build account name from given name and family name
        given_name = data.get("given_name", "")
        family_name = data.get("family_name", "")
        account_name = f"{given_name} {family_name}".strip() or data.get("name", "LinkedIn User")

        return {
            "account_name": account_name,
            "external_id": external_id,
        }

    @classmethod
    def refresh_access_token(cls, refresh_token):
        return None
