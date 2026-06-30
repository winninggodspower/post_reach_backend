import uuid

from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from utils.cache_keys import CacheKeys
from utils.custom_logger import CustomLogger, log_exceptions
from utils.http import APIError

OAUTH_STATE_TTL = 600  # 10 minutes


class InstagramService(SocialAccountService):
    APP_ID = settings.INSTAGRAM_APP_ID
    APP_SECRET = settings.INSTAGRAM_APP_SECRET
    BASE_URL = "https://graph.instagram.com"
    redirect_uri = settings.REDIRECT_URI["instagram"]

    REQUIRED_PERMISSIONS = {
        "instagram_business_basic",
        "instagram_business_content_publish",
    }

    @classmethod
    def generate_auth_url(cls, user_id):
        """
        Generates an Instagram OAuth authorization URL with CSRF state protection.
        Stores the state in cache for later verification.
        The redirect URI is resolved from settings.REDIRECT_URI["instagram"].
        """
        redirect_uri = cls.redirect_uri
        state = str(uuid.uuid4())
        cache.set(CacheKeys.instagram_oauth_state(user_id), state, OAUTH_STATE_TTL)

        params = {
            "client_id": cls.APP_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(cls.REQUIRED_PERMISSIONS),
            "response_type": "code",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://api.instagram.com/oauth/authorize?{query_string}"

    @classmethod
    def exchange_code_for_token(cls, auth_code, redirect_uri):
        short_lived_token_data = cls._get_short_lived_token(auth_code, redirect_uri)
        long_lived_token_data = cls._get_long_lived_token(
            short_lived_token_data["access_token"]
        )

        return {
            "access_token": long_lived_token_data["access_token"],
            "expires_in": long_lived_token_data["expires_in"],
            "user_id": short_lived_token_data["user_id"],
        }, []

    @classmethod
    def _get_short_lived_token(cls, auth_code, redirect_uri):
        try:
            response_data = cls().post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": cls.APP_ID,
                    "client_secret": cls.APP_SECRET,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": auth_code,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Instagram short-lived token exchange failed",
                extra={"operation": "_get_short_lived_token"},
            )
            raise ValueError(str(e)) from e

        if "access_token" not in response_data:
            raise ValueError(
                response_data.get("error_message", "Could not get short-lived token")
            )

        return response_data

    @classmethod
    def _get_long_lived_token(cls, short_lived_token):
        try:
            response_data = cls().get(
                "/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": cls.APP_SECRET,
                    "access_token": short_lived_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Instagram long-lived token exchange failed",
                extra={"operation": "_get_long_lived_token"},
            )
            raise ValueError(str(e)) from e

        if "access_token" not in response_data:
            raise ValueError(
                response_data.get("error", {}).get(
                    "message", "Could not get long-lived token"
                )
            )

        return response_data

    @classmethod
    def refresh_access_token(cls, long_lived_token: str):
        try:
            response_data = cls().get(
                "/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": long_lived_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Instagram access token refresh failed",
                extra={"operation": "refresh_access_token"},
            )
            raise ValueError(str(e)) from e

        if "access_token" not in response_data:
            raise ValueError(
                response_data.get("error", {}).get("message", "Unknown error")
            )

        return {
            "access_token": response_data["access_token"],
            "refresh_token": None,
            "expires_in": response_data["expires_in"],
        }

    @classmethod
    def fetch_user_info(cls, access_token: str) -> dict:
        """
        Fetches the Instagram user profile info using the access token.
        Returns a dict with 'account_name' and 'external_id'.
        """
        try:
            response_data = cls().get(
                "/me",
                params={
                    "fields": "id,username",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Failed to fetch Instagram user info",
                extra={"operation": "fetch_user_info"},
            )
            raise ValueError(f"Failed to fetch Instagram user info: {str(e)}") from e

        external_id = response_data.get("id")
        if not external_id:
            raise ValueError("Failed to retrieve Instagram user ID")

        return {
            "account_name": response_data.get("username", ""),
            "external_id": str(external_id),
        }

    @classmethod
    def publish_video(cls, access_token, instagram_account_id, video_url, caption=""):
        """
        Publish a video to Instagram using the Content Publishing API.
        Step 1: Create a media container. The publishing is handled asynchronously.

        :param access_token: Valid Instagram Graph API access token.
        :param instagram_account_id: Instagram Business/Creator account ID.
        :param video_url: Public URL of the video file.
        :param caption: Video caption (optional).
        :return: Dict with 'platform_post_id' (container ID) and 'status'.
        """
        try:
            container_response = cls().post(
                f"/{instagram_account_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption or "",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Instagram media container creation failed",
                extra={"operation": "publish_video"},
            )
            raise ValueError(
                f"Instagram media container creation failed: {str(e)}"
            ) from e

        container_id = container_response.get("id")
        if not container_id:
            raise ValueError("Instagram did not return a media container ID")

        return {"platform_post_id": container_id, "status": "processing"}

    @classmethod
    def publish_photo(cls, access_token, instagram_account_id, photo_urls, caption=""):
        """
        Publish a photo (or carousel of photos) to Instagram.
        Step 1: Creates Image/Carousel container. Publishing is handled asynchronously.

        :param access_token: Valid Instagram Graph API access token.
        :param instagram_account_id: Instagram Business/Creator account ID.
        :param photo_urls: List of public/presigned URLs of the photo files.
        :param caption: Photo caption (optional).
        :return: Dict with 'platform_post_id' (container ID) and 'status'.
        """
        if len(photo_urls) == 1:
            # Single photo: create IMAGE container
            try:
                container_response = cls().post(
                    f"/{instagram_account_id}/media",
                    data={
                        "media_type": "IMAGE",
                        "image_url": photo_urls[0],
                        "caption": caption or "",
                        "access_token": access_token,
                    },
                )
            except APIError as e:
                CustomLogger.exception(
                    "Instagram photo container creation failed",
                    extra={"operation": "publish_photo"},
                )
                raise ValueError(
                    f"Instagram photo container creation failed: {str(e)}"
                ) from e

            container_id = container_response.get("id")
            if not container_id:
                raise ValueError("Instagram did not return a media container ID")

            return {"platform_post_id": container_id, "status": "processing"}

        # Multiple photos: create a CAROUSEL
        # Step 1: Create an IMAGE container for each photo
        child_container_ids = []
        for url in photo_urls:
            try:
                container_response = cls().post(
                    f"/{instagram_account_id}/media",
                    data={
                        "media_type": "IMAGE",
                        "image_url": url,
                        "is_carousel_item": "true",
                        "access_token": access_token,
                    },
                )
            except APIError as e:
                CustomLogger.exception(
                    "Instagram carousel image container failed",
                    extra={"operation": "publish_photo", "url": url},
                )
                raise ValueError(
                    f"Instagram carousel image container creation failed: {str(e)}"
                ) from e

            child_id = container_response.get("id")
            if not child_id:
                raise ValueError(
                    f"Instagram did not return container ID for image: {url}"
                )
            child_container_ids.append(child_id)

        # Step 2: Create a CAROUSEL container with children
        try:
            carousel_container = cls().post(
                f"/{instagram_account_id}/media",
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_container_ids),
                    "caption": caption or "",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Instagram carousel container creation failed",
                extra={"operation": "publish_photo"},
            )
            raise ValueError(
                f"Instagram carousel container creation failed: {str(e)}"
            ) from e

        carousel_id = carousel_container.get("id")
        if not carousel_id:
            raise ValueError("Instagram did not return a carousel container ID")

        return {"platform_post_id": carousel_id, "status": "processing"}

    @classmethod
    def check_container_status(cls, access_token: str, container_id: str) -> str:
        """
        Checks the status of a media container.
        Returns: "FINISHED", "IN_PROGRESS", "ERROR", etc.
        """
        try:
            response_data = cls().get(
                f"/{container_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Failed to check Instagram container status",
                extra={"operation": "check_container_status", "container_id": container_id},
            )
            raise ValueError(f"Failed to check container status: {str(e)}") from e

        status_code = response_data.get("status_code")
        if status_code == "ERROR":
            status_desc = response_data.get("status", "Unknown error")
            raise ValueError(f"Instagram container processing failed: {status_desc}")

        return status_code

    @classmethod
    def publish_container(
        cls, access_token: str, instagram_account_id: str, container_id: str
    ) -> dict:
        """
        Publishes a finished container to the feed.
        """
        try:
            publish_response = cls().post(
                f"/{instagram_account_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Instagram container publish failed",
                extra={"operation": "publish_container", "container_id": container_id},
            )
            raise ValueError(f"Instagram media publish failed: {str(e)}") from e

        media_id = publish_response.get("id", container_id)
        return {"platform_post_id": media_id}
