import uuid

import google_auth_oauthlib
import googleapiclient.discovery
import oauthlib.oauth2.rfc6749.errors
from django.conf import settings
from django.core.cache import cache
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from integrations.providers.base import SocialAccountService
from utils.cache_keys import CacheKeys
from utils.custom_logger import CustomLogger

OAUTH_STATE_TTL = 600  # 10 minutes


class YoutubeService(SocialAccountService):
    CLIENT_ID = settings.GOOGLE_CLIENT_ID
    CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET

    REQUIRED_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]
    redirect_uri = settings.REDIRECT_URI["youtube"]

    @classmethod
    def generate_auth_url(cls, user_id):
        """
        Generates a YouTube OAuth authorization URL with CSRF state protection.
        Stores the state in cache for later verification.
        The redirect URI is resolved from settings.REDIRECT_URI["youtube"].
        """
        redirect_uri = cls.redirect_uri
        state = str(uuid.uuid4())
        cache.set(CacheKeys.youtube_oauth_state(user_id), state, OAUTH_STATE_TTL)

        client_config = {
            "web": {
                "client_id": cls.CLIENT_ID,
                "client_secret": cls.CLIENT_SECRET,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            client_config,
            scopes=cls.REQUIRED_SCOPES,
            redirect_uri=redirect_uri,
        )

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            state=state,
            prompt="consent",
        )

        return authorization_url

    @classmethod
    def _fetch_channel_info(cls, credentials):
        """
        Fetch the YouTube channel name and external ID using the YouTube Data API v3.

        Returns a dict with 'account_name' and 'external_id'.
        Raises ValueError if the channel info cannot be retrieved.
        """
        try:
            youtube = googleapiclient.discovery.build(
                "youtube", "v3", credentials=credentials
            )
            channels_response = (
                youtube.channels()
                .list(
                    part="snippet",
                    mine=True,
                )
                .execute()
            )

            items = channels_response.get("items", [])
            if not items:
                raise ValueError(
                    "No YouTube channel found for this account. "
                    "Please ensure you have a YouTube channel associated with your Google account."
                )

            channel = items[0]
            snippet = channel.get("snippet", {})
            return {
                "account_name": snippet.get("title", ""),
                "external_id": channel.get("id", ""),
            }
        except ValueError:
            raise
        except Exception as e:
            CustomLogger.exception(
                "Failed to fetch YouTube channel info",
                extra={"operation": "_fetch_channel_info"},
            )
            raise ValueError(f"Failed to fetch YouTube channel information: {str(e)}")

    @classmethod
    def connect_account(cls, *, user, auth_code, state=None, brand=None):
        """
        Complete the YouTube OAuth connection flow:
        1. Verify the OAuth state (CSRF protection)
        2. Resolve the brand
        3. Exchange the auth code for tokens
        4. Fetch channel info (account name and external ID)
        5. Save the social account

        The redirect URI is resolved from settings.REDIRECT_URI["youtube"].

        Returns the created/updated SocialAccount instance.
        Raises ValueError or PermissionError on failure.
        """
        from social_accounts.models import SocialAccount

        # 1. State verification
        if state:
            cached_state = cache.get(CacheKeys.youtube_oauth_state(user.id))
            if not cached_state or state != cached_state:
                raise ValueError("Invalid state parameter. Possible CSRF attack.")
            cache.delete(CacheKeys.youtube_oauth_state(user.id))

        # 2. Brand resolution
        resolved_brand = cls._resolve_brand(user, brand)

        # 3. Exchange code for token
        credentials, missing_scopes = cls.exchange_code_for_token(
            auth_code=auth_code,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        # 4. Fetch channel info (account name and external ID)
        channel_info = cls._fetch_channel_info(credentials)

        # 5. Save account
        account, _ = SocialAccount.objects.update_or_create(
            brand=resolved_brand,
            platform="youtube",
            defaults={
                "account_name": channel_info["account_name"],
                "external_id": channel_info["external_id"],
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expires_at": credentials.expiry,
                "scope": " ".join(credentials.scopes),
            },
        )

        return account

    @classmethod
    def exchange_code_for_token(cls, auth_code):
        redirect_uri = cls.redirect_uri
        try:
            client_config = {
                "web": {
                    "client_id": cls.CLIENT_ID,
                    "client_secret": cls.CLIENT_SECRET,
                    "redirect_uris": [redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }

            flow = google_auth_oauthlib.flow.Flow.from_client_config(
                client_config,
                scopes=cls.REQUIRED_SCOPES,
                redirect_uri=redirect_uri,
            )

            flow.fetch_token(code=auth_code)

            credentials = flow.credentials

            missing_scopes = set(cls.REQUIRED_SCOPES) - set(credentials.scopes)

            return credentials, missing_scopes
        except oauthlib.oauth2.rfc6749.errors.InvalidGrantError:
            CustomLogger.exception(
                "YouTube authorization code exchange failed due to invalid grant",
                extra={
                    "operation": "exchange_code_for_token",
                    "redirect_uri": redirect_uri,
                },
            )
            raise ValueError("Authorization code has expired or is invalid")
        except Exception as e:
            CustomLogger.exception(
                "Unexpected YouTube token exchange failure",
                extra={
                    "operation": "exchange_code_for_token",
                    "redirect_uri": redirect_uri,
                },
            )
            raise Exception(f"Error exchanging code for token: {str(e)}")

    @classmethod
    def refresh_access_token(cls, refresh_token):
        credentials = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cls.CLIENT_ID,
            client_secret=cls.CLIENT_SECRET,
            scopes=cls.REQUIRED_SCOPES,
        )

        request = Request()
        credentials.refresh(request)

        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_in": credentials.expiry,
        }

    @classmethod
    def get_youtube_client(cls, access_token):
        credentials = Credentials(
            token=access_token,
            client_id=cls.CLIENT_ID,
            client_secret=cls.CLIENT_SECRET,
            scopes=cls.REQUIRED_SCOPES,
        )
        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    @classmethod
    def publish_video(cls, access_token, video_bytes, title, description=""):
        """
        Upload a video to YouTube.

        :param access_token: Valid YouTube access token.
        :param video_bytes: Raw video file bytes.
        :param title: Video title (required by YouTube).
        :param description: Video description (optional).
        :return: Dict with 'platform_post_id' (the YouTube video ID).
        """
        import io

        from googleapiclient.http import MediaIoBaseUpload

        youtube = cls.get_youtube_client(access_token)

        body = {
            "snippet": {
                "title": title[:100],  # YouTube title limit
                "description": description or "",
            },
            "status": {
                "privacyStatus": "public",
            },
        }

        media = MediaIoBaseUpload(
            io.BytesIO(video_bytes),
            mimetype="video/*",
            resumable=True,
        )

        try:
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )
            response = request.execute()
            return {"platform_post_id": response["id"]}
        except Exception as e:
            CustomLogger.exception(
                "YouTube video upload failed",
                extra={"operation": "publish_video"},
            )
            raise ValueError(f"YouTube video upload failed: {str(e)}") from e
