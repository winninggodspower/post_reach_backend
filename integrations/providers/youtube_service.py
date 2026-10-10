import os
import uuid
from collections.abc import Iterable
from datetime import UTC
from typing import Any

import google_auth_oauthlib
import googleapiclient.discovery
import httpx
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
    RESUMABLE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

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
            thumbnails = snippet.get("thumbnails", {})
            return {
                "account_name": snippet.get("title", ""),
                "external_id": channel.get("id", ""),
                "profile_picture_url": (
                    thumbnails.get("high", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                ),
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
        expiry = credentials.expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)

        account, _ = SocialAccount.objects.update_or_create(
            brand=resolved_brand,
            platform="youtube",
            defaults={
                "account_name": channel_info["account_name"],
                "external_id": channel_info["external_id"],
                "profile_picture_url": channel_info.get("profile_picture_url"),
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expires_at": expiry,
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

            # Google may return different scopes (e.g. if the user unchecks optional scopes
            # on the consent screen or previously granted extra scopes). Allow scope changes
            # so oauthlib doesn't raise ScopeChangeWarning exceptions.
            os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

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

        # Ensure expiry is timezone-aware UTC
        expiry = credentials.expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)

        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_in": expiry,
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
    def _initiate_resumable_upload(
        cls,
        access_token: str,
        total_bytes: int,
        title: str,
        description: str = "",
        privacy_status: str = "public",
        media_type: str = "video/mp4",
    ) -> str:
        """
        Initiates a resumable upload session with YouTube API.
        Returns the resumable session URL (Location header).
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(total_bytes),
            "X-Upload-Content-Type": media_type,
        }
        body = {
            "snippet": {
                "title": title[:100] if title else "Untitled Video",
                "description": description or "",
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }
        params = {
            "uploadType": "resumable",
            "part": "snippet,status",
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                cls.RESUMABLE_UPLOAD_URL,
                params=params,
                headers=headers,
                json=body,
            )
            if resp.status_code not in (200, 201):
                CustomLogger.error(
                    "YouTube resumable upload INIT failed",
                    extra={"status_code": resp.status_code, "response": resp.text},
                )
                raise ValueError(
                    f"YouTube video upload INIT failed ({resp.status_code}): {resp.text}"
                )

            upload_url = resp.headers.get("Location")
            if not upload_url:
                raise ValueError(
                    "YouTube resumable upload did not return a Location header"
                )
            return upload_url

    @classmethod
    def _upload_resumable_chunk(
        cls,
        upload_url: str,
        chunk: bytes,
        start_byte: int,
        total_bytes: int,
        media_type: str = "video/mp4",
    ) -> dict | None:
        """
        Uploads a single chunk to the YouTube resumable upload URL.
        Returns the video metadata dict on completion (HTTP 200/201),
        None on intermediate chunk (HTTP 308 Resume Incomplete),
        or raises ValueError on failure.
        """
        end_byte = start_byte + len(chunk) - 1
        headers = {
            "Content-Length": str(len(chunk)),
            "Content-Range": f"bytes {start_byte}-{end_byte}/{total_bytes}",
            "Content-Type": media_type,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.put(upload_url, headers=headers, content=chunk)

            if resp.status_code in (200, 201):
                return resp.json()
            elif resp.status_code == 308:
                return None
            else:
                CustomLogger.error(
                    f"YouTube video chunk upload failed at bytes {start_byte}-{end_byte}",
                    extra={"status_code": resp.status_code, "response": resp.text},
                )
                raise ValueError(
                    f"YouTube video chunk upload failed ({resp.status_code}): {resp.text}"
                )

    @classmethod
    def _stream_chunks_from_response(
        cls, stream_resp, chunk_size: int = 5 * 1024 * 1024
    ):
        """
        Buffers incoming network chunks from an httpx stream into chunks of chunk_size (5MB).
        """
        buf = bytearray()
        for chunk in stream_resp.iter_bytes(chunk_size=64 * 1024):
            if not chunk:
                continue
            buf.extend(chunk)
            while len(buf) >= chunk_size:
                yield bytes(buf[:chunk_size])
                del buf[:chunk_size]
        if buf:
            yield bytes(buf)

    @classmethod
    def _chunk_bytes(cls, data: bytes, chunk_size: int = 5 * 1024 * 1024):
        """
        Yields chunk_size slices from raw bytes in memory.
        """
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    @classmethod
    def _upload_thumbnail(
        cls, access_token: str, video_id: str, thumbnail_bytes: bytes
    ) -> None:
        """
        Uploads an image thumbnail to YouTube for the given video.
        """
        import io

        from googleapiclient.http import MediaIoBaseUpload

        try:
            youtube = cls.get_youtube_client(access_token)
            thumb_media = MediaIoBaseUpload(
                io.BytesIO(thumbnail_bytes),
                mimetype="image/jpeg",
                resumable=True,
            )
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=thumb_media,
            ).execute()
        except Exception as thumb_err:
            CustomLogger.warning(
                "YouTube video thumbnail upload failed",
                extra={
                    "operation": "publish_video",
                    "video_id": video_id,
                    "error": str(thumb_err),
                },
            )

    @classmethod
    def publish_video(
        cls,
        access_token: str,
        video_input: bytes | str | None = None,
        title: str = "",
        description: str = "",
        thumbnail_bytes: bytes | None = None,
        video_bytes: bytes | None = None,
        privacy_status: str = "public",
        media_type: str = "video/mp4",
    ) -> dict:
        """
        Upload a video to YouTube using chunked resumable upload (5MB per chunk).
        Streams directly from remote URL if video_input is a URL, avoiding high RAM usage.

        :param access_token: Valid YouTube access token.
        :param video_input: Presigned video URL (str) or raw bytes.
        :param title: Video title (required by YouTube).
        :param description: Video description (optional).
        :param thumbnail_bytes: Raw thumbnail image bytes (optional).
        :param video_bytes: Backward-compatible alias for video_input.
        :param privacy_status: "public", "unlisted", or "private".
        :param media_type: Video MIME type (default "video/mp4").
        :return: Dict with 'platform_post_id' (the YouTube video ID).
        """
        raw_source = video_input if video_input is not None else video_bytes
        if not raw_source:
            raise ValueError("No video source provided to publish_video")

        chunk_size = 5 * 1024 * 1024  # 5 MB per chunk (multiple of 256 KB)

        if isinstance(raw_source, bytes):
            video_id = cls._execute_chunked_upload(
                access_token=access_token,
                total_bytes=len(raw_source),
                chunks_iter=cls._chunk_bytes(raw_source, chunk_size),
                title=title,
                description=description,
                privacy_status=privacy_status,
                media_type=media_type,
            )
        else:
            # raw_source is a URL (str)
            try:
                with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                    with client.stream("GET", raw_source) as stream_resp:
                        stream_resp.raise_for_status()
                        content_length = stream_resp.headers.get("Content-Length")
                        if content_length:
                            total_bytes = int(content_length)
                            chunks_iter = cls._stream_chunks_from_response(
                                stream_resp, chunk_size
                            )
                        else:
                            # Fallback if Content-Length header is missing from upstream
                            downloaded = stream_resp.read()
                            total_bytes = len(downloaded)
                            chunks_iter = cls._chunk_bytes(downloaded, chunk_size)

                        video_id = cls._execute_chunked_upload(
                            access_token=access_token,
                            total_bytes=total_bytes,
                            chunks_iter=chunks_iter,
                            title=title,
                            description=description,
                            privacy_status=privacy_status,
                            media_type=media_type,
                        )
            except Exception as e:
                CustomLogger.exception(
                    "YouTube video upload failed",
                    extra={"operation": "publish_video", "error": str(e)},
                )
                raise ValueError(f"YouTube video upload failed: {str(e)}") from e

        if thumbnail_bytes:
            cls._upload_thumbnail(access_token, video_id, thumbnail_bytes)

        return {"platform_post_id": video_id}

    @classmethod
    def _execute_chunked_upload(
        cls,
        access_token: str,
        total_bytes: int,
        chunks_iter: Iterable[bytes],
        title: str,
        description: str,
        privacy_status: str,
        media_type: str,
    ) -> str:
        """
        Executes the resumable upload: initiates session, iterates chunks, and returns the video ID.
        """
        upload_url = cls._initiate_resumable_upload(
            access_token=access_token,
            total_bytes=total_bytes,
            title=title,
            description=description,
            privacy_status=privacy_status,
            media_type=media_type,
        )
        video_id = None
        start_byte = 0
        for chunk in chunks_iter:
            result = cls._upload_resumable_chunk(
                upload_url=upload_url,
                chunk=chunk,
                start_byte=start_byte,
                total_bytes=total_bytes,
                media_type=media_type,
            )
            if result and "id" in result:
                video_id = result["id"]
            start_byte += len(chunk)

        if not video_id:
            raise ValueError(
                "YouTube video upload completed without returning a video ID"
            )
        return video_id

    @classmethod
    def get_post_metrics(
        cls, platform_post_id: str, access_token: str
    ) -> dict[str, Any]:
        """
        Fetches live video statistics (views, likes, comments) from YouTube Data API v3.
        """
        credentials = Credentials(token=access_token)
        youtube = googleapiclient.discovery.build(
            "youtube", "v3", credentials=credentials
        )
        response = (
            youtube.videos()
            .list(part="statistics", id=platform_post_id)
            .execute()
        )
        items = response.get("items", [])
        if not items:
            return {
                "views": 0,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "raw": response,
            }

        stats = items[0].get("statistics", {})
        return {
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "shares": 0,
            "raw": stats,
        }

