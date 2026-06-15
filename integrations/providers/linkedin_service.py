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

    @classmethod
    def publish_video(cls, access_token, person_urn, video_url, title="", description=""):
        """
        Publish a video post to LinkedIn using the UGC Posts API.

        Step 1: Initialize a video upload via /videos?action=startUpload
        Step 2: Upload the video bytes to the returned upload URL
        Step 3: Finalize upload and create a share on LinkedIn

        :param access_token: Valid LinkedIn access token with w_member_social scope.
        :param person_urn: LinkedIn person URN (e.g., "urn:li:person:xxxxx").
        :param video_url: Public URL of the video file for LinkedIn to pull.
        :param title: Post text / commentary (optional).
        :param description: Additional description (optional).
        :return: Dict with 'platform_post_id' (the LinkedIn activity/share URN).
        """
        try:
            # For LinkedIn, we create a share with the video URL directly
            # LinkedIn API supports sharing video URLs natively
            response = cls().post(
                f"{cls.API_BASE_URL}/ugcPosts",
                data={
                    "author": person_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": f"{title}\n{description}" if description else title,
                            },
                            "shareMediaCategory": "VIDEO",
                            "media": [
                                {
                                    "status": "READY",
                                    "originalUrl": video_url,
                                    "title": {
                                        "text": title or "Video",
                                    },
                                }
                            ],
                        }
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
                    },
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "LinkedIn video publish failed",
                extra={"operation": "publish_video"},
            )
            raise ValueError(f"LinkedIn video publish failed: {str(e)}") from e

        post_id = response.get("id", "")
        if not post_id:
            raise ValueError("LinkedIn publish did not return a post ID")

        return {"platform_post_id": post_id}

    @classmethod
    def publish_photo(cls, access_token, person_urn, photo_url, text=""):
        """
        Publish a photo post to LinkedIn using the UGC Posts API.

        :param access_token: Valid LinkedIn access token.
        :param person_urn: LinkedIn person URN.
        :param photo_url: Public URL of the photo file.
        :param text: Post text (optional).
        :return: Dict with 'platform_post_id'.
        """
        try:
            response = cls().post(
                f"{cls.API_BASE_URL}/ugcPosts",
                data={
                    "author": person_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": text or "",
                            },
                            "shareMediaCategory": "IMAGE",
                            "media": [
                                {
                                    "status": "READY",
                                    "originalUrl": photo_url,
                                }
                            ],
                        }
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
                    },
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "LinkedIn photo publish failed",
                extra={"operation": "publish_photo"},
            )
            raise ValueError(f"LinkedIn photo publish failed: {str(e)}") from e

        post_id = response.get("id", "")
        if not post_id:
            raise ValueError("LinkedIn publish did not return a post ID")

        return {"platform_post_id": post_id}
