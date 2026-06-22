import json
import uuid

from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from social_accounts.utils.cache_keys import facebook_oauth_state
from utils.custom_logger import CustomLogger
from utils.http import APIError

OAUTH_STATE_TTL = 600  # 10 minutes


class FacebookService(SocialAccountService):
    CLIENT_ID = settings.FACEBOOK_APP_ID
    CLIENT_SECRET = settings.FACEBOOK_APP_SECRET
    BASE_URL = "https://graph.facebook.com/v25.0"
    redirect_uri = settings.REDIRECT_URI["facebook"]

    REQUIRED_SCOPES = {
        "pages_show_list",
        # "pages_manage_engagement",
        "pages_read_engagement",
        "pages_manage_posts",
    }

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
            "scope": ",".join(cls.REQUIRED_SCOPES),
            "response_type": "code",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://www.facebook.com/v18.0/dialog/oauth?{query_string}"

    @classmethod
    def refresh_access_token(self, refresh_token):
        return None

    @classmethod
    def exchange_code_for_token(cls, code, redirect_uri):
        """
        Exchanges an authorization code for a long-lived access token.
        Step 1: Exchange the code for a short-lived token (via Facebook's /oauth/access_token endpoint).
        Step 2: Exchange the short-lived token for a long-lived token.
        """
        try:
            # Step 1: code → short-lived token
            short_lived_data = cls().get(
                "/oauth/access_token",
                params={
                    "client_id": cls.CLIENT_ID,
                    "redirect_uri": redirect_uri,
                    "client_secret": cls.CLIENT_SECRET,
                    "code": code,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Facebook code exchange failed",
                extra={"operation": "exchange_code_for_token"},
            )
            raise ValueError(str(e)) from e

        if "access_token" not in short_lived_data:
            raise ValueError(
                short_lived_data.get("error", {}).get(
                    "message", "Failed to exchange code for short-lived token"
                )
            )

        short_lived_token = short_lived_data["access_token"]

        # Step 2: short-lived → long-lived
        return cls.exchange_short_lived_token(short_lived_token)

    @classmethod
    def exchange_short_lived_token(cls, short_lived_token):
        try:
            is_valid, missing_permissions = cls.verify_granted_scope(short_lived_token)
        except APIError as e:
            CustomLogger.exception(
                "Facebook permission verification failed",
                extra={"operation": "verify_granted_scope"},
            )
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
            CustomLogger.exception(
                "Facebook token exchange failed",
                extra={"operation": "exchange_short_lived_token"},
            )
            raise ValueError(str(e)) from e

        if "access_token" not in data:
            raise ValueError(data.get("error", {}).get("message", "Unknown error"))

        return data["access_token"], int(
            data.get("expires_in", 5184000)
        )  # default expires_in to 60days

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

        missing_permissions = cls.REQUIRED_SCOPES - granted_permissions

        return (not bool(missing_permissions), missing_permissions)

    @classmethod
    def get_facebook_pages(cls, access_token):
        """
        Fetches the Facebook Pages managed by this access token.
        Returns a list of dicts with 'id' and 'name' for each page.
        """
        try:
            data = cls().get(
                "/me/accounts",
                params={
                    "access_token": access_token,
                    "fields": "id,name,picture,access_token",
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Failed to fetch Facebook pages",
                extra={"operation": "get_facebook_pages"},
            )
            raise ValueError(f"Failed to fetch Facebook pages: {str(e)}") from e

        pages = data.get("data", [])
        if not pages:
            raise ValueError("No Facebook pages found for this account")

        return [
            {
                "id": page["id"],
                "name": page["name"],
                "access_token": page["access_token"],
                "picture_url": page.get("picture", {}).get("data", {}).get("url", None),
            }
            for page in pages
        ]

    @classmethod
    def publish_video(
        cls, page_access_token, page_id, video_url, title="", description=""
    ):
        """
        Publish a video to a Facebook Page.

        :param page_access_token: Access token for the Facebook Page.
        :param page_id: Facebook Page ID.
        :param video_url: Public/presigned URL of the video file.
        :param title: Video title (optional).
        :param description: Video description (optional).
        :return: Dict with 'platform_post_id' (the Facebook post/video ID).
        """
        try:
            data = cls().post(
                f"/{page_id}/videos",
                data={
                    "file_url": video_url,
                    "title": title or "",
                    "description": description or "",
                    "access_token": page_access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Facebook video publish failed",
                extra={"operation": "publish_video"},
            )
            raise ValueError(f"Facebook video publish failed: {str(e)}") from e

        post_id = data.get("id", "")
        if not post_id:
            raise ValueError("Facebook video publish did not return a post ID")

        return {"platform_post_id": post_id}

    @classmethod
    def publish_photo(cls, page_access_token, page_id, photo_urls, text=""):
        """
        Publish a photo (or multiple photos) to a Facebook Page.

        For a single photo, posts directly to /{page_id}/photos.
        For multiple photos, creates individual photo objects with published=false
        and then posts them together in a feed post with attached_media.

        :param page_access_token: Access token for the Facebook Page.
        :param page_id: Facebook Page ID.
        :param photo_urls: List of public/presigned URLs of the photo files.
        :param text: Caption text (optional).
        :return: Dict with 'platform_post_id' (the Facebook post ID).
        """
        if len(photo_urls) == 1:
            # Single photo: use the simple /photos endpoint
            try:
                data = cls().post(
                    f"/{page_id}/photos",
                    data={
                        "url": photo_urls[0],
                        "message": text or "",
                        "access_token": page_access_token,
                    },
                )
            except APIError as e:
                CustomLogger.exception(
                    "Facebook photo publish failed",
                    extra={"operation": "publish_photo"},
                )
                raise ValueError(f"Facebook photo publish failed: {str(e)}") from e

            post_id = data.get("id", "") or data.get("post_id", "")
            if not post_id:
                raise ValueError("Facebook photo publish did not return a post ID")
            return {"platform_post_id": post_id}

        # Multiple photos: create each photo as unpublished, then post a feed
        media_fbids = []
        for url in photo_urls:
            try:
                photo_data = cls().post(
                    f"/{page_id}/photos",
                    data={
                        "url": url,
                        "published": "false",
                        "access_token": page_access_token,
                    },
                )
            except APIError as e:
                CustomLogger.exception(
                    "Facebook multi-photo item creation failed",
                    extra={"operation": "publish_photo", "url": url},
                )
                raise ValueError(f"Facebook photo creation failed: {str(e)}") from e

            fbid = photo_data.get("id")
            if not fbid:
                raise ValueError(f"Facebook did not return an ID for photo: {url}")
            media_fbids.append(fbid)

        # Post the feed with attached media
        try:
            feed_data = cls().post(
                f"/{page_id}/feed",
                data={
                    "message": text or "",
                    "attached_media": json.dumps(
                        [{"media_fbid": fbid} for fbid in media_fbids]
                    ),
                    "access_token": page_access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Facebook multi-photo feed publish failed",
                extra={"operation": "publish_photo"},
            )
            raise ValueError(
                f"Facebook multi-photo feed publish failed: {str(e)}"
            ) from e

        post_id = feed_data.get("id", "")
        if not post_id:
            raise ValueError("Facebook multi-photo publish did not return a post ID")
        return {"platform_post_id": post_id}
