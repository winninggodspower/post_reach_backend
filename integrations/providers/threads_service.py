import uuid

from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from utils.cache_keys import CacheKeys
from utils.custom_logger import CustomLogger
from utils.http import APIError

OAUTH_STATE_TTL = 600  # 10 minutes


class ThreadsService(SocialAccountService):
    APP_ID = settings.THREADS_APP_ID
    APP_SECRET = settings.THREADS_APP_SECRET
    BASE_URL = "https://graph.threads.net"
    redirect_uri = settings.REDIRECT_URI.get("threads", "")

    REQUIRED_PERMISSIONS = {
        "threads_basic",
        "threads_content_publish",
    }

    @classmethod
    def generate_auth_url(cls, user_id):
        """
        Generates a Threads OAuth authorization URL with CSRF state protection.
        Stores the state in cache for later verification.
        The redirect URI is resolved from settings.REDIRECT_URI["threads"].
        """
        redirect_uri = cls.redirect_uri
        state = str(uuid.uuid4())
        cache.set(CacheKeys.threads_oauth_state(user_id), state, OAUTH_STATE_TTL)

        params = {
            "client_id": cls.APP_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(cls.REQUIRED_PERMISSIONS),
            "response_type": "code",
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://threads.net/oauth/authorize?{query_string}"

    @classmethod
    def exchange_code_for_token(cls, auth_code, redirect_uri):
        """
        Exchanges the authorization code for a short-lived token,
        then immediately exchanges it for a 60-day long-lived access token.
        """
        short_lived_token_data = cls._get_short_lived_token(auth_code, redirect_uri)
        long_lived_token_data = cls._get_long_lived_token(
            short_lived_token_data["access_token"]
        )

        return {
            "access_token": long_lived_token_data["access_token"],
            "expires_in": long_lived_token_data.get("expires_in", 5184000),
            "user_id": short_lived_token_data.get("user_id"),
        }, []

    @classmethod
    def _get_short_lived_token(cls, auth_code, redirect_uri):
        try:
            response_data = cls().post(
                "https://graph.threads.net/oauth/access_token",
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
                "Threads short-lived token exchange failed",
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
                    "grant_type": "th_exchange_token",
                    "client_secret": cls.APP_SECRET,
                    "access_token": short_lived_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Threads long-lived token exchange failed",
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
        """
        Refreshes a valid long-lived Threads access token.
        Extends validity by an additional 60 days.
        """
        try:
            response_data = cls().get(
                "/refresh_access_token",
                params={
                    "grant_type": "th_refresh_token",
                    "access_token": long_lived_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Threads access token refresh failed",
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
            "expires_in": response_data.get("expires_in", 5184000),
        }

    @classmethod
    def fetch_user_info(cls, access_token: str) -> dict:
        """
        Fetches the Threads user profile info using the access token.
        Returns a dict with 'account_name', 'external_id', and 'profile_picture_url'.
        """
        try:
            response_data = cls().get(
                "/v1.0/me",
                params={
                    "fields": "id,username,name,threads_profile_picture_url",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Failed to fetch Threads user info",
                extra={"operation": "fetch_user_info"},
            )
            raise ValueError(f"Failed to fetch Threads user info: {str(e)}") from e

        external_id = response_data.get("id")
        if not external_id:
            raise ValueError("Failed to retrieve Threads user ID")

        return {
            "account_name": response_data.get("username")
            or response_data.get("name", ""),
            "external_id": str(external_id),
            "profile_picture_url": response_data.get("threads_profile_picture_url"),
        }

    @classmethod
    def get_publishing_limit(
        cls,
        access_token: str,
        threads_user_id: str,
        fields: str = "quota_usage,config",
    ) -> dict:
        """
        Checks a profile's current Threads API rate limit usage.
        Query fields can include:
        - quota_usage, config (posts)
        - reply_quota_usage, reply_config (replies)
        - delete_quota_usage, delete_config (deletions)
        - location_search_quota_usage, location_search_config (location search)
        """
        try:
            return cls().get(
                f"/v1.0/{threads_user_id}/threads_publishing_limit",
                params={
                    "fields": fields,
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Failed to query Threads publishing limit",
                extra={
                    "operation": "get_publishing_limit",
                    "threads_user_id": threads_user_id,
                },
            )
            raise ValueError(
                f"Failed to check Threads publishing limit: {str(e)}"
            ) from e

    @classmethod
    def publish_text(
        cls, access_token: str, threads_user_id: str, text: str
    ) -> dict:
        """
        Publish a text post to Threads.
        Text posts are limited to 500 characters.
        """
        if len(text) > 500:
            raise ValueError(
                f"Threads text posts are limited to 500 characters. Current length: {len(text)}"
            )

        try:
            container_response = cls().post(
                f"/v1.0/{threads_user_id}/threads",
                data={
                    "media_type": "TEXT",
                    "text": text,
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Threads text container creation failed",
                extra={"operation": "publish_text"},
            )
            raise ValueError(
                f"Threads text container creation failed: {str(e)}"
            ) from e

        container_id = container_response.get("id")
        if not container_id:
            raise ValueError("Threads did not return a container ID")

        # Publish the container immediately
        return cls.publish_container(
            access_token=access_token,
            threads_user_id=threads_user_id,
            container_id=container_id,
        )

    @classmethod
    def publish_photo(
        cls,
        access_token: str,
        threads_user_id: str,
        photo_urls: list[str],
        text: str = "",
    ) -> dict:
        """
        Publish a photo (or carousel of photos) to Threads.
        Step 1: Creates Image/Carousel container. Publishing is handled asynchronously.

        :param access_token: Valid Threads Graph API access token.
        :param threads_user_id: Threads user ID.
        :param photo_urls: List of public URLs of the photo files.
        :param text: Caption text (optional, max 500 characters).
        :return: Dict with 'platform_post_id' (container ID) and 'status'.
        """
        if text and len(text) > 500:
            raise ValueError(
                f"Threads caption is limited to 500 characters. Current length: {len(text)}"
            )

        if not photo_urls:
            raise ValueError("At least one photo URL is required.")

        if len(photo_urls) > 20:
            raise ValueError(
                f"Threads carousel posts support a maximum of 20 children. Provided: {len(photo_urls)}"
            )

        if len(photo_urls) == 1:
            try:
                container_response = cls().post(
                    f"/v1.0/{threads_user_id}/threads",
                    data={
                        "media_type": "IMAGE",
                        "image_url": photo_urls[0],
                        "text": text or "",
                        "access_token": access_token,
                    },
                )
            except APIError as e:
                CustomLogger.exception(
                    "Threads photo container creation failed",
                    extra={"operation": "publish_photo"},
                )
                raise ValueError(
                    f"Threads photo container creation failed: {str(e)}"
                ) from e

            container_id = container_response.get("id")
            if not container_id:
                raise ValueError("Threads did not return a container ID")

            return {"platform_post_id": container_id, "status": "processing"}

        # Multiple photos: Carousel post (2 to 20 children)
        child_container_ids = []
        for url in photo_urls:
            try:
                item_response = cls().post(
                    f"/v1.0/{threads_user_id}/threads",
                    data={
                        "media_type": "IMAGE",
                        "image_url": url,
                        "is_carousel_item": "true",
                        "access_token": access_token,
                    },
                )
            except APIError as e:
                CustomLogger.exception(
                    "Threads carousel item container creation failed",
                    extra={"operation": "publish_photo", "url": url},
                )
                raise ValueError(
                    f"Threads carousel item creation failed: {str(e)}"
                ) from e

            child_id = item_response.get("id")
            if not child_id:
                raise ValueError(
                    f"Threads did not return container ID for image: {url}"
                )
            child_container_ids.append(child_id)

        try:
            carousel_container = cls().post(
                f"/v1.0/{threads_user_id}/threads",
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_container_ids),
                    "text": text or "",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Threads carousel container creation failed",
                extra={"operation": "publish_photo"},
            )
            raise ValueError(
                f"Threads carousel container creation failed: {str(e)}"
            ) from e

        carousel_id = carousel_container.get("id")
        if not carousel_id:
            raise ValueError("Threads did not return a carousel container ID")

        return {"platform_post_id": carousel_id, "status": "processing"}

    @classmethod
    def publish_video(
        cls,
        access_token: str,
        threads_user_id: str,
        video_url: str,
        text: str = "",
    ) -> dict:
        """
        Publish a video to Threads using the Content Publishing API.
        Step 1: Create a media container. The publishing is handled asynchronously.

        :param access_token: Valid Threads Graph API access token.
        :param threads_user_id: Threads user ID.
        :param video_url: Public URL of the video file.
        :param text: Video caption (optional, max 500 characters).
        :return: Dict with 'platform_post_id' (container ID) and 'status'.
        """
        if text and len(text) > 500:
            raise ValueError(
                f"Threads caption is limited to 500 characters. Current length: {len(text)}"
            )

        try:
            container_response = cls().post(
                f"/v1.0/{threads_user_id}/threads",
                data={
                    "media_type": "VIDEO",
                    "video_url": video_url,
                    "text": text or "",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Threads video container creation failed",
                extra={"operation": "publish_video"},
            )
            raise ValueError(
                f"Threads video container creation failed: {str(e)}"
            ) from e

        container_id = container_response.get("id")
        if not container_id:
            raise ValueError("Threads did not return a video container ID")

        return {"platform_post_id": container_id, "status": "processing"}

    @classmethod
    def check_container_status(cls, access_token: str, container_id: str) -> str:
        """
        Checks the status of a media container.
        Returns: "FINISHED", "IN_PROGRESS", "ERROR", etc.
        """
        try:
            response_data = cls().get(
                f"/v1.0/{container_id}",
                params={
                    "fields": "status,error_message",
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Failed to check Threads container status",
                extra={
                    "operation": "check_container_status",
                    "container_id": container_id,
                },
            )
            raise ValueError(
                f"Failed to check container status: {str(e)}"
            ) from e

        status = response_data.get("status")
        if status == "ERROR":
            status_desc = (
                response_data.get("error_message")
                or "Unknown error"
            )
            raise ValueError(f"Threads container processing failed: {status_desc}")

        return status or ""

    @classmethod
    def publish_container(
        cls, access_token: str, threads_user_id: str, container_id: str
    ) -> dict:
        """
        Publishes a finished container to the Threads feed.
        """
        try:
            publish_response = cls().post(
                f"/v1.0/{threads_user_id}/threads_publish",
                data={
                    "creation_id": container_id,
                    "access_token": access_token,
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "Threads container publish failed",
                extra={
                    "operation": "publish_container",
                    "container_id": container_id,
                },
            )
            raise ValueError(f"Threads media publish failed: {str(e)}") from e

        media_id = publish_response.get("id", container_id)
        return {"platform_post_id": media_id, "status": "published"}

    @classmethod
    def get_permalink(cls, access_token: str, media_id: str) -> str:
        """
        Fetches the permalink (URL) for a published media object.
        """
        try:
            response_data = cls().get(
                f"/v1.0/{media_id}",
                params={
                    "fields": "permalink",
                    "access_token": access_token,
                },
            )
        except Exception as e:
            CustomLogger.exception(
                "Failed to fetch Threads permalink",
                extra={
                    "operation": "get_permalink",
                    "media_id": media_id,
                },
            )
            return ""

        return response_data.get("permalink", "")
