import time
from collections.abc import Iterable
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache
from requests_oauthlib import OAuth1Session

from integrations.providers.base import SocialAccountService
from utils.cache_keys import CacheKeys
from utils.custom_logger import CustomLogger

OAUTH_STATE_TTL = 600  # 10 minutes


class TwitterService(SocialAccountService):
    API_KEY = getattr(settings, "TWITTER_API_KEY", "")
    API_SECRET = getattr(settings, "TWITTER_API_SECRET", "")
    BASE_URL = "https://api.x.com"
    UPLOAD_BASE_URL = "https://upload.twitter.com/1.1"
    redirect_uri = settings.REDIRECT_URI.get("twitter", "")

    REQUEST_TOKEN_URL = "https://api.x.com/oauth/request_token"
    AUTHORIZE_URL = "https://api.x.com/oauth/authorize"
    ACCESS_TOKEN_URL = "https://api.x.com/oauth/access_token"

    @classmethod
    def _get_oauth_session(
        cls,
        resource_owner_key: str | None = None,
        resource_owner_secret: str | None = None,
        callback_uri: str | None = None,
        verifier: str | None = None,
    ) -> OAuth1Session:
        return OAuth1Session(
            client_key=cls.API_KEY,
            client_secret=cls.API_SECRET,
            resource_owner_key=resource_owner_key,
            resource_owner_secret=resource_owner_secret,
            callback_uri=callback_uri,
            verifier=verifier,
        )

    @classmethod
    def generate_auth_url(cls, user_id: int) -> str:
        """
        Initiates the 3-legged OAuth 1.0a flow with X.
        Fetches a temporary request token, caches the oauth_token_secret,
        and returns the authorization URL for user redirection.
        """
        redirect_uri = cls.redirect_uri
        oauth = cls._get_oauth_session(callback_uri=redirect_uri)

        try:
            fetch_response = oauth.fetch_request_token(cls.REQUEST_TOKEN_URL)
        except Exception as e:
            CustomLogger.exception(
                "Failed to fetch Twitter request token",
                extra={"operation": "generate_auth_url", "error": str(e)},
            )
            raise ValueError(f"Failed to initiate Twitter authorization: {e}") from e

        oauth_token = fetch_response.get("oauth_token")
        oauth_token_secret = fetch_response.get("oauth_token_secret")

        if not oauth_token or not oauth_token_secret:
            raise ValueError(
                "Twitter response missing oauth_token or oauth_token_secret."
            )

        # Cache the request token secret so connect() can sign the access token exchange
        cache.set(
            CacheKeys.twitter_request_token_secret(oauth_token),
            oauth_token_secret,
            OAUTH_STATE_TTL,
        )

        return oauth.authorization_url(cls.AUTHORIZE_URL)

    @classmethod
    def exchange_tokens(cls, oauth_token: str, oauth_verifier: str) -> dict[str, str]:
        """
        Exchanges the temporary request token and verifier for permanent user access tokens.
        Retrieves the cached request token secret, verifies, and returns token credentials.
        """
        cached_secret_key = CacheKeys.twitter_request_token_secret(oauth_token)
        oauth_token_secret = cache.get(cached_secret_key)

        if not oauth_token_secret:
            raise ValueError(
                "Invalid or expired authorization request. Please restart the connection flow."
            )

        cache.delete(cached_secret_key)

        oauth = cls._get_oauth_session(
            resource_owner_key=oauth_token,
            resource_owner_secret=oauth_token_secret,
            verifier=oauth_verifier,
        )

        try:
            tokens = oauth.fetch_access_token(cls.ACCESS_TOKEN_URL)
        except Exception as e:
            CustomLogger.exception(
                "Failed to exchange Twitter access token",
                extra={"operation": "exchange_tokens", "error": str(e)},
            )
            raise ValueError(f"Twitter access token exchange failed: {e}") from e

        access_token = tokens.get("oauth_token")
        access_token_secret = tokens.get("oauth_token_secret")

        if not access_token or not access_token_secret:
            raise ValueError(
                "Twitter response missing permanent access token or secret."
            )

        return {
            "access_token": access_token,
            "access_token_secret": access_token_secret,
            "user_id": str(tokens.get("user_id", "")),
            "screen_name": tokens.get("screen_name", ""),
        }

    @classmethod
    def fetch_user_info(
        cls, access_token: str, access_token_secret: str
    ) -> dict[str, Any]:
        """
        Retrieves user information from X using user-context credentials.
        First tries X API v2 /2/users/me, then falls back to /1.1/account/verify_credentials.json.
        """
        oauth = cls._get_oauth_session(
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret,
        )

        # Attempt v2 /2/users/me
        try:
            resp = oauth.get(
                f"{cls.BASE_URL}/2/users/me",
                params={
                    "user.fields": "profile_image_url,name,username,verified,verified_type"
                },
                timeout=15.0,
            )
            if resp.status_code == 200:
                user_data = resp.json().get("data", {})
                profile_image = user_data.get("profile_image_url", "")
                if profile_image:
                    profile_image = profile_image.replace("_normal", "")

                username = user_data.get("username", "")
                name = user_data.get("name", "")
                display_name = f"@{username}" if username else name
                verified = user_data.get("verified", False)
                verified_type = user_data.get("verified_type")
                is_premium = (
                    verified_type in ("blue", "business", "government")
                    or verified is True
                )

                return {
                    "account_name": display_name,
                    "external_id": str(user_data.get("id", "")),
                    "profile_picture_url": profile_image or None,
                    "username": username,
                    "name": name,
                    "is_premium": is_premium,
                    "verified": verified,
                    "verified_type": verified_type,
                }
        except Exception as e:
            CustomLogger.warning(
                "X API v2 /2/users/me call failed; trying v1.1 fallback",
                extra={"error": str(e)},
            )

        # Fallback to v1.1 account/verify_credentials.json
        try:
            resp = oauth.get(
                f"{cls.BASE_URL}/1.1/account/verify_credentials.json",
                timeout=15.0,
            )
            if resp.status_code == 200:
                user_data = resp.json()
                profile_image = user_data.get(
                    "profile_image_url_https"
                ) or user_data.get("profile_image_url", "")
                if profile_image:
                    profile_image = profile_image.replace("_normal", "")

                screen_name = user_data.get("screen_name", "")
                display_name = (
                    f"@{screen_name}" if screen_name else user_data.get("name", "")
                )
                verified = user_data.get("verified", False)
                is_blue_verified = user_data.get("is_blue_verified", False)
                is_premium = bool(is_blue_verified or verified)

                return {
                    "account_name": display_name,
                    "external_id": str(
                        user_data.get("id_str") or user_data.get("id", "")
                    ),
                    "profile_picture_url": profile_image or None,
                    "username": screen_name,
                    "name": user_data.get("name", ""),
                    "is_premium": is_premium,
                    "verified": verified,
                    "verified_type": "blue" if is_blue_verified else None,
                }
            resp.raise_for_status()
        except Exception as e:
            CustomLogger.exception(
                "Failed to fetch Twitter user info",
                extra={"operation": "fetch_user_info", "error": str(e)},
            )
            raise ValueError(f"Failed to fetch Twitter profile information: {e}") from e

    @classmethod
    def refresh_access_token(cls, refresh_token: str, /) -> dict[str, Any] | None:
        """
        OAuth 1.0a access tokens on X do not expire and do not need to be refreshed.
        Always returns None.
        """
        return None

    @classmethod
    def post_tweet(
        cls,
        access_token: str,
        access_token_secret: str,
        text: str = "",
        media_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Publishes a post (tweet) using X API v2 /2/tweets.
        """
        oauth = cls._get_oauth_session(
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret,
        )

        payload: dict[str, Any] = {}
        if text:
            payload["text"] = text

        if media_ids:
            payload["media"] = {"media_ids": [str(m) for m in media_ids]}

        if not payload:
            raise ValueError(
                "Cannot publish an empty tweet (no text or media provided)."
            )

        try:
            resp = oauth.post(
                f"{cls.BASE_URL}/2/tweets",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
        except Exception as e:
            CustomLogger.exception(
                "Network error creating X tweet",
                extra={"operation": "post_tweet", "error": str(e)},
            )
            raise ValueError(f"Failed to publish tweet: {e}") from e

        if resp.status_code not in (200, 201):
            error_detail = resp.text
            try:
                error_json = resp.json()
                error_detail = (
                    error_json.get("detail")
                    or error_json.get("title")
                    or error_json.get("errors")
                    or resp.text
                )
            except Exception:
                pass
            CustomLogger.error(
                "X API /2/tweets rejected post",
                extra={"status_code": resp.status_code, "response": resp.text},
            )
            raise ValueError(f"X API error ({resp.status_code}): {error_detail}")

        data = resp.json().get("data", {})
        tweet_id = str(data.get("id", ""))
        return {
            "id": tweet_id,
            "platform_post_id": tweet_id,
            "text": data.get("text", text),
            "status": "published",
        }

    @classmethod
    def _download_media_bytes(cls, media_input: bytes | str) -> bytes:
        if isinstance(media_input, bytes):
            return media_input
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(media_input)
            resp.raise_for_status()
            return resp.content

    @classmethod
    def upload_photo(
        cls,
        access_token: str,
        access_token_secret: str,
        media_input: bytes | str,
    ) -> str:
        """
        Uploads an image to X via the media upload endpoint.
        Returns the media_id_string.
        """
        media_bytes = cls._download_media_bytes(media_input)

        oauth = cls._get_oauth_session(
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret,
        )

        files = {"media": ("image.jpg", media_bytes, "image/jpeg")}
        data = {"media_category": "tweet_image"}

        try:
            resp = oauth.post(
                f"{cls.UPLOAD_BASE_URL}/media/upload.json",
                files=files,
                data=data,
                timeout=60.0,
            )
        except Exception as e:
            CustomLogger.exception(
                "Network error uploading photo to X",
                extra={"operation": "upload_photo", "error": str(e)},
            )
            raise ValueError(f"Failed to upload image to X: {e}") from e

        if resp.status_code not in (200, 201, 202):
            CustomLogger.error(
                "X media upload failed",
                extra={"status_code": resp.status_code, "response": resp.text},
            )
            raise ValueError(f"X photo upload failed ({resp.status_code}): {resp.text}")

        media_id = resp.json().get("media_id_string") or str(
            resp.json().get("media_id")
        )
        return media_id

    @classmethod
    def _init_media_upload(
        cls, oauth: OAuth1Session, total_bytes: int, media_type: str
    ) -> str:
        init_data = {
            "command": "INIT",
            "total_bytes": str(total_bytes),
            "media_type": media_type,
            "media_category": "tweet_video",
        }
        init_resp = oauth.post(
            f"{cls.UPLOAD_BASE_URL}/media/upload.json",
            data=init_data,
            timeout=30.0,
        )
        if init_resp.status_code not in (200, 201, 202):
            CustomLogger.error(
                "Twitter video upload INIT failed",
                extra={
                    "status_code": init_resp.status_code,
                    "response": init_resp.text,
                },
            )
            raise ValueError(
                f"Twitter video upload INIT failed ({init_resp.status_code}): {init_resp.text}"
            )

        media_id = init_resp.json().get("media_id_string") or str(
            init_resp.json().get("media_id")
        )
        return media_id

    @classmethod
    def _append_media_chunk(
        cls, oauth: OAuth1Session, media_id: str, segment_id: int, chunk: bytes
    ) -> None:
        append_data = {
            "command": "APPEND",
            "media_id": media_id,
            "segment_index": str(segment_id),
        }
        append_files = {"media": chunk}
        append_resp = oauth.post(
            f"{cls.UPLOAD_BASE_URL}/media/upload.json",
            data=append_data,
            files=append_files,
            timeout=60.0,
        )
        if append_resp.status_code not in (200, 204):
            CustomLogger.error(
                f"Twitter video upload APPEND segment {segment_id} failed",
                extra={
                    "status_code": append_resp.status_code,
                    "response": append_resp.text,
                },
            )
            raise ValueError(
                f"Twitter video upload APPEND segment {segment_id} failed ({append_resp.status_code}): {append_resp.text}"
            )

    @classmethod
    def _finalize_media_upload(cls, oauth: OAuth1Session, media_id: str) -> str:
        finalize_data = {
            "command": "FINALIZE",
            "media_id": media_id,
        }
        finalize_resp = oauth.post(
            f"{cls.UPLOAD_BASE_URL}/media/upload.json",
            data=finalize_data,
            timeout=30.0,
        )
        if finalize_resp.status_code not in (200, 201):
            CustomLogger.error(
                "Twitter video upload FINALIZE failed",
                extra={
                    "status_code": finalize_resp.status_code,
                    "response": finalize_resp.text,
                },
            )
            raise ValueError(
                f"Twitter video upload FINALIZE failed ({finalize_resp.status_code}): {finalize_resp.text}"
            )

        finalize_json = finalize_resp.json()
        processing_info = finalize_json.get("processing_info")

        if processing_info:
            cls._check_video_status(oauth, media_id, processing_info)

        return media_id

    @classmethod
    def _stream_chunks_from_response(
        cls, stream_resp, chunk_size: int = 5 * 1024 * 1024
    ):
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
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    @classmethod
    def upload_video(
        cls,
        access_token: str,
        access_token_secret: str,
        media_input: bytes | str,
        media_type: str = "video/mp4",
    ) -> str:
        """
        Uploads a video to X using chunked upload (INIT, APPEND, FINALIZE, and STATUS checking).
        Streams directly from remote URL in 5MB chunks without buffering entire file in memory.
        Returns the media_id_string.
        """
        oauth = cls._get_oauth_session(
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret,
        )
        chunk_size = (
            5 * 1024 * 1024
        )  # 5 MB per chunk (X/Twitter recommended max segment size)

        if isinstance(media_input, bytes):
            return cls._execute_chunked_upload(
                oauth=oauth,
                total_bytes=len(media_input),
                chunks_iter=cls._chunk_bytes(media_input, chunk_size),
                media_type=media_type,
            )

        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                with client.stream("GET", media_input) as stream_resp:
                    stream_resp.raise_for_status()
                    content_length = stream_resp.headers.get("Content-Length")
                    if content_length:
                        total_bytes = int(content_length)
                        chunks_iter = cls._stream_chunks_from_response(
                            stream_resp, chunk_size
                        )
                    else:
                        # Fallback if Content-Length header is not provided by upstream server
                        video_bytes = stream_resp.read()
                        total_bytes = len(video_bytes)
                        chunks_iter = cls._chunk_bytes(video_bytes, chunk_size)

                    return cls._execute_chunked_upload(
                        oauth=oauth,
                        total_bytes=total_bytes,
                        chunks_iter=chunks_iter,
                        media_type=media_type,
                    )
        except Exception as e:
            CustomLogger.exception(
                "Failed to stream and upload video to X",
                extra={"operation": "upload_video", "error": str(e)},
            )
            raise

    @classmethod
    def _execute_chunked_upload(
        cls,
        oauth: OAuth1Session,
        total_bytes: int,
        chunks_iter: Iterable[bytes],
        media_type: str,
    ) -> str:
        """
        Executes INIT, iterates chunks for APPEND, and FINALIZE.
        """
        media_id = cls._init_media_upload(oauth, total_bytes, media_type)
        for segment_id, chunk in enumerate(chunks_iter):
            cls._append_media_chunk(oauth, media_id, segment_id, chunk)
        return cls._finalize_media_upload(oauth, media_id)

    @classmethod
    def _check_video_status(
        cls,
        oauth: OAuth1Session,
        media_id: str,
        initial_processing_info: dict[str, Any],
        max_attempts: int = 30,
    ):
        """
        Polls the X media upload status until the video has completed processing or fails.
        """
        state = initial_processing_info.get("state")
        check_after_secs = initial_processing_info.get("check_after_secs", 5)

        for _ in range(max_attempts):
            if state in ("succeeded", "completed"):
                return
            if state == "failed":
                error_msg = initial_processing_info.get("error", {}).get(
                    "message", "Twitter video processing failed."
                )
                raise ValueError(f"Twitter video processing failed: {error_msg}")

            time.sleep(check_after_secs)

            status_resp = oauth.get(
                f"{cls.UPLOAD_BASE_URL}/media/upload.json",
                params={"command": "STATUS", "media_id": media_id},
                timeout=15.0,
            )
            if status_resp.status_code != 200:
                raise ValueError(f"Failed to check video status: {status_resp.text}")

            processing_info = status_resp.json().get("processing_info", {})
            state = processing_info.get("state")
            check_after_secs = processing_info.get("check_after_secs", 5)

        if state not in ("succeeded", "completed"):
            raise TimeoutError("Twitter video processing timed out.")

    @classmethod
    def get_post_metrics(
        cls,
        platform_post_id: str,
        access_token: str,
        access_token_secret: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetches live tweet metrics (views/impressions, likes, retweets, replies, bookmarks) from X/Twitter API v2.
        """
        views = 0
        likes = 0
        comments = 0
        shares = 0
        saves = 0
        raw_data = {}

        try:
            if access_token_secret:
                oauth = cls._get_oauth_session(
                    resource_owner_key=access_token,
                    resource_owner_secret=access_token_secret,
                )
                resp = oauth.get(
                    f"{cls.BASE_URL}/2/tweets/{platform_post_id}",
                    params={"tweet.fields": "public_metrics"},
                    timeout=10.0,
                )
            else:
                resp = httpx.get(
                    f"{cls.BASE_URL}/2/tweets/{platform_post_id}",
                    params={"tweet.fields": "public_metrics"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0,
                )
            if resp.status_code == 200:
                raw_data = resp.json()
                metrics = raw_data.get("data", {}).get("public_metrics", {})
                views = int(metrics.get("impression_count", 0) or 0)
                likes = int(metrics.get("like_count", 0) or 0)
                comments = int(metrics.get("reply_count", 0) or 0)
                shares = int(metrics.get("retweet_count", 0) or 0) + int(
                    metrics.get("quote_count", 0) or 0
                )
                saves = int(metrics.get("bookmark_count", 0) or 0)
        except Exception:
            pass

        return {
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "saves": saves,
            "raw": raw_data,
        }
