import uuid

import httpx
from django.conf import settings
from django.core.cache import cache

from integrations.providers.base import SocialAccountService
from social_accounts.utils.cache_keys import linkedin_oauth_state
from utils.custom_logger import CustomLogger
from utils.http import APIError

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
            CustomLogger.exception(
                "LinkedIn token exchange failed",
                extra={
                    "operation": "exchange_code_for_token",
                    "redirect_uri": redirect_uri,
                },
            )
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
            CustomLogger.exception(
                "Failed to fetch LinkedIn user info",
                extra={"operation": "fetch_user_info"},
            )
            raise ValueError(f"Failed to fetch LinkedIn user info: {str(e)}") from e

        external_id = data.get("sub")
        if not external_id:
            raise ValueError("Failed to retrieve LinkedIn user ID")

        # Build account name from given name and family name
        given_name = data.get("given_name", "")
        family_name = data.get("family_name", "")
        account_name = f"{given_name} {family_name}".strip() or data.get(
            "name", "LinkedIn User"
        )

        return {
            "account_name": account_name,
            "external_id": external_id,
        }

    @classmethod
    def refresh_access_token(cls, refresh_token):
        return None

    # ------------------------------------------------------------------
    # Media upload helpers (shared by image and video publishing)
    # ------------------------------------------------------------------

    @classmethod
    def _download_media_binary(cls, media_url):
        """
        Downloads binary data from the given URL.

        :param media_url: Public URL of the media file.
        :return: Raw bytes of the media.
        """
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                response = client.get(media_url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            CustomLogger.exception(
                "Failed to download media for LinkedIn upload",
                extra={"operation": "_download_media_binary", "media_url": media_url},
            )
            raise ValueError(
                f"Failed to download media from {media_url}: {str(e)}"
            ) from e

    @classmethod
    def _register_media_upload(cls, access_token, person_urn, recipe):
        """
        Registers a media (image/video) upload with LinkedIn and returns
        the upload URL and media asset URN.

        :param access_token: Valid LinkedIn access token.
        :param person_urn: LinkedIn person URN.
        :param recipe: The digital media recipe URN, e.g.
                       "urn:li:digitalmediaRecipe:feedshare-image" or
                       "urn:li:digitalmediaRecipe:feedshare-video".
        :return: Tuple of (upload_url, asset_urn).
        """
        try:
            response = cls().post(
                f"{cls.API_BASE_URL}/assets?action=registerUpload",
                json_data={
                    "registerUploadRequest": {
                        "recipes": [recipe],
                        "owner": person_urn,
                        "serviceRelationships": [
                            {
                                "relationshipType": "OWNER",
                                "identifier": "urn:li:userGeneratedContent",
                            }
                        ],
                    }
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
            )
        except APIError as e:
            CustomLogger.exception(
                "LinkedIn media registration failed",
                extra={"operation": "_register_media_upload", "recipe": recipe},
            )
            raise ValueError(f"LinkedIn media registration failed: {str(e)}") from e

        try:
            value = response["value"]
            upload_mechanism = value["uploadMechanism"][
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
            ]
            upload_url = upload_mechanism["uploadUrl"]
            asset_urn = value["asset"]
        except (KeyError, TypeError) as e:
            raise ValueError(
                f"LinkedIn media registration response missing expected fields: {e}"
            ) from e

        return upload_url, asset_urn

    @classmethod
    def _upload_media_to_linkedin(cls, upload_url, media_binary):
        """
        Uploads raw binary data to the LinkedIn-provided upload URL.

        :param upload_url: The upload URL obtained from registerUpload.
        :param media_binary: Raw bytes of the media file.
        """
        try:
            with httpx.Client(timeout=300.0) as client:
                response = client.request(
                    method="POST",
                    url=upload_url,
                    content=media_binary,
                    headers={
                        "Content-Type": "application/octet-stream",
                    },
                )
                response.raise_for_status()
        except Exception as e:
            CustomLogger.exception(
                "LinkedIn media binary upload failed",
                extra={"operation": "_upload_media_to_linkedin"},
            )
            raise ValueError(f"LinkedIn media binary upload failed: {str(e)}") from e

    # ------------------------------------------------------------------
    # Publishing methods
    # ------------------------------------------------------------------

    @classmethod
    def publish_video(
        cls, access_token, person_urn, video_url, title="", description=""
    ):
        """
        Publish a video post to LinkedIn using the UGC Posts API.

        LinkedIn requires a multi-step process for video sharing:
        1. Register the video upload via /assets?action=registerUpload
        2. Download the video from the source URL
        3. Upload the video binary to LinkedIn's upload URL
        4. Create the share with the media asset URN

        :param access_token: Valid LinkedIn access token with w_member_social scope.
        :param person_urn: LinkedIn person URN (e.g., "urn:li:person:xxxxx").
        :param video_url: Public URL of the video file to download and upload.
        :param title: Post text / commentary (optional).
        :param description: Additional description (optional).
        :return: Dict with 'platform_post_id' (the LinkedIn activity/share URN).
        """
        # Step 1: Register the video upload with LinkedIn
        upload_url, asset_urn = cls._register_media_upload(
            access_token, person_urn, "urn:li:digitalmediaRecipe:feedshare-video"
        )

        # Step 2: Download the video binary from the source URL
        video_binary = cls._download_media_binary(video_url)

        # Step 3: Upload the video binary to LinkedIn
        cls._upload_media_to_linkedin(upload_url, video_binary)

        # Step 4: Create the share post with the media asset URN
        try:
            response = cls().post(
                f"{cls.API_BASE_URL}/ugcPosts",
                json_data={
                    "author": person_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": (
                                    f"{title}\n{description}" if description else title
                                ),
                            },
                            "shareMediaCategory": "VIDEO",
                            "media": [
                                {
                                    "status": "READY",
                                    "media": asset_urn,
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
    def publish_photo(cls, access_token, person_urn, photo_urls, text=""):
        """
        Publish a photo (or multiple photos) to LinkedIn using the UGC Posts API.

        LinkedIn requires a multi-step process for image sharing:
        1. Register each image upload via /assets?action=registerUpload
        2. Download each image from its source URL
        3. Upload each image binary to LinkedIn's upload URL
        4. Create the share with all media asset URNs

        :param access_token: Valid LinkedIn access token with w_member_social scope.
        :param person_urn: LinkedIn person URN (e.g., "urn:li:person:xxxxx").
        :param photo_urls: List of public/presigned URLs of the photo files.
        :param text: Post text (optional).
        :return: Dict with 'platform_post_id'.
        """
        # Step 1-3: Register, download, and upload each image
        asset_urns = []
        for photo_url in photo_urls:
            upload_url, asset_urn = cls._register_media_upload(
                access_token, person_urn, "urn:li:digitalmediaRecipe:feedshare-image"
            )
            image_binary = cls._download_media_binary(photo_url)
            cls._upload_media_to_linkedin(upload_url, image_binary)
            asset_urns.append(asset_urn)

        # Step 4: Create the share post with all media asset URNs
        try:
            response = cls().post(
                f"{cls.API_BASE_URL}/ugcPosts",
                json_data={
                    "author": person_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": text or "",
                            },
                            "shareMediaCategory": "IMAGE",
                            "media": [
                                {"status": "READY", "media": asset_urn}
                                for asset_urn in asset_urns
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
