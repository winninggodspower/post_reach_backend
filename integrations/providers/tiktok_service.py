import hashlib
import secrets
import string
import uuid

from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from social_accounts.utils.cache_keys import tiktok_code_verifier, tiktok_oauth_state
from utils.http import APIError
from utils.custom_logger import CustomLogger

# TikTok OAuth flow can take a while (user needs to log in, authorize, then get redirected back).
# Use a generous TTL to avoid the code_verifier expiring before the callback completes.
OAUTH_STATE_TTL = 600  # 10 minutes in seconds

def _generate_code_verifier(length=128):
    """
    Generate a high-entropy cryptographic random string using unreserved characters
    [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
    with a minimum length of 43 characters and a maximum length of 128 characters.
    """
    characters = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(characters) for _ in range(length))


def _generate_code_challenge(code_verifier):
    """
    Create the code challenge by hashing the code verifier using hex encoding of SHA256.
    TikTok only supports S256 as code_challenge_method.
    """
    return hashlib.sha256(code_verifier.encode("ascii")).hexdigest()


class TiktokService(SocialAccountService):
    CLIENT_KEY = settings.TIKTOK_CLIENT_KEY
    CLIENT_SECRET = settings.TIKTOK_CLIENT_SECRET
    # TikTok's OAuth token endpoints live under open.tiktokapis.com
    BASE_URL = "https://open.tiktokapis.com"
    # User info endpoint uses the older open-api base
    USER_INFO_BASE_URL = "https://open-api.tiktok.com"
    redirect_uri = settings.REDIRECT_URI["tiktok"]

    REQUIRED_SCOPES = [
        "user.info.basic",
        "video.publish",
        "video.upload",
    ]

    @classmethod
    def generate_auth_url(cls, user_id):
        """
        Generates a TikTok OAuth authorization URL with:
        - CSRF state protection (stored in cache)
        - PKCE code_challenge (S256) with code_verifier stored in cache
        The redirect URI is resolved from settings.REDIRECT_URI["tiktok"].
        """
        redirect_uri = cls.redirect_uri
        state = str(uuid.uuid4())
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)

        cache.set(tiktok_oauth_state(user_id), state, OAUTH_STATE_TTL)
        cache.set(tiktok_code_verifier(user_id), code_verifier, OAUTH_STATE_TTL)

        params = {
            "client_key": cls.CLIENT_KEY,
            "response_type": "code",
            "scope": ",".join(cls.REQUIRED_SCOPES),
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://www.tiktok.com/v2/auth/authorize/?{query_string}"

    @classmethod
    def exchange_code_for_token(cls, code, user_id):
        """
        Exchanges the authorization code for an access token.

        TikTok expects a POST with Content-Type: application/x-www-form-urlencoded
        to https://open.tiktokapis.com/v2/oauth/token/

        Retrieves the stored code_verifier from cache for PKCE verification.
        """
        code_verifier = cache.get(tiktok_code_verifier(user_id))
        if not code_verifier:
            raise ValueError("Code verifier not found. Please restart the OAuth flow.")

        try:
            response = cls().post(
                "/v2/oauth/token/",
                data={
                    "client_key": cls.CLIENT_KEY,
                    "client_secret": cls.CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": cls.redirect_uri,
                    "code_verifier": code_verifier,
                },
            )
        except APIError as e:
            CustomLogger.exception("TikTok token exchange failed", extra={"operation": "exchange_code_for_token"})
            raise ValueError(str(e)) from e
        if not response:
            raise ValueError("Error while fetching access token from TikTok")

        # Clean up the used code_verifier
        cache.delete(tiktok_code_verifier(user_id))

        return response

    @classmethod
    def fetch_user_info(cls, access_token):
        """
        Fetch the TikTok user's info (open_id, display name, avatar, etc.)
        using the TikTok /oauth/userinfo/ endpoint.

        Returns a dict with 'account_name' and 'external_id'.
        Raises ValueError if the user info cannot be retrieved.
        """
        try:
            # User info uses the older open-api base URL
            from utils.http import BaseHTTPClient

            client = BaseHTTPClient(base_url=cls.USER_INFO_BASE_URL)
            data = client.get(
                "/oauth/userinfo/",
                params={"access_token": access_token},
            )
        except APIError as e:
            CustomLogger.exception(
                "Failed to fetch TikTok user info",
                extra={"operation": "fetch_user_info"},
            )
            raise ValueError(f"Failed to fetch TikTok user info: {str(e)}") from e

        if not data or "data" not in data:
            raise ValueError("Unable to retrieve TikTok user information")

        user_data = data["data"]
        return {
            "account_name": user_data.get("display_name", "") or user_data.get("username", ""),
            "external_id": user_data.get("open_id", ""),
        }

    @classmethod
    def refresh_access_token(cls, refresh_token):
        try:
            response = cls().post(
                "/v2/oauth/token/",
                data={
                    "client_key": cls.CLIENT_KEY,
                    "client_secret": cls.CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        except APIError as e:
            CustomLogger.exception("TikTok access token refresh failed", extra={"operation": "refresh_access_token"})
            raise ValueError(str(e)) from e
        if not response:
            raise ValueError("Error while refreshing access token from TikTok")

        return response
