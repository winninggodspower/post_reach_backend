from unittest.mock import MagicMock

import pytest
from django.core.cache import cache

from integrations.providers.twitter_service import TwitterService
from utils.cache_keys import CacheKeys

pytestmark = pytest.mark.django_db


class TestTwitterServiceAuth:
    """Tests for TwitterService OAuth 1.0a methods."""

    def test_generate_auth_url_success(self, mocker):
        mock_oauth = MagicMock()
        mock_oauth.fetch_request_token.return_value = {
            "oauth_token": "mock_req_token_123",
            "oauth_token_secret": "mock_req_secret_456",
            "oauth_callback_confirmed": "true",
        }
        mock_oauth.authorization_url.return_value = (
            "https://api.x.com/oauth/authorize?oauth_token=mock_req_token_123"
        )
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        url = TwitterService.generate_auth_url(user_id=1)

        assert url == "https://api.x.com/oauth/authorize?oauth_token=mock_req_token_123"
        cached_secret = cache.get(
            CacheKeys.twitter_request_token_secret("mock_req_token_123")
        )
        assert cached_secret == "mock_req_secret_456"

    def test_generate_auth_url_failure(self, mocker):
        mock_oauth = MagicMock()
        mock_oauth.fetch_request_token.side_effect = Exception(
            "X API Connection Refused"
        )
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        with pytest.raises(
            ValueError, match="Failed to initiate Twitter authorization"
        ):
            TwitterService.generate_auth_url(user_id=1)

    def test_exchange_tokens_success(self, mocker):
        cache.set(
            CacheKeys.twitter_request_token_secret("mock_token_abc"),
            "cached_secret_xyz",
            timeout=60,
        )

        mock_oauth = MagicMock()
        mock_oauth.fetch_access_token.return_value = {
            "oauth_token": "permanent_token_789",
            "oauth_token_secret": "permanent_secret_987",
            "user_id": "12345678",
            "screen_name": "x_developer",
        }
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        result = TwitterService.exchange_tokens(
            oauth_token="mock_token_abc", oauth_verifier="valid_verifier"
        )

        assert result["access_token"] == "permanent_token_789"
        assert result["access_token_secret"] == "permanent_secret_987"
        assert result["user_id"] == "12345678"
        assert result["screen_name"] == "x_developer"
        # Secret should have been popped/deleted from cache
        assert (
            cache.get(CacheKeys.twitter_request_token_secret("mock_token_abc")) is None
        )

    def test_exchange_tokens_missing_cached_secret(self):
        with pytest.raises(
            ValueError, match="Invalid or expired authorization request"
        ):
            TwitterService.exchange_tokens(
                oauth_token="non_existent_token", oauth_verifier="any_verifier"
            )

    def test_exchange_tokens_x_api_error(self, mocker):
        cache.set(
            CacheKeys.twitter_request_token_secret("mock_token_abc"),
            "cached_secret_xyz",
            timeout=60,
        )

        mock_oauth = MagicMock()
        mock_oauth.fetch_access_token.side_effect = Exception("401 Unauthorized")
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        with pytest.raises(ValueError, match="Twitter access token exchange failed"):
            TwitterService.exchange_tokens(
                oauth_token="mock_token_abc", oauth_verifier="bad_verifier"
            )


class TestTwitterServiceUserInfo:
    """Tests for TwitterService profile fetching."""

    def test_fetch_user_info_v2_success(self, mocker):
        mock_oauth = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "id": "123456",
                "name": "Jane Doe",
                "username": "janedoe",
                "profile_image_url": "https://pbs.twimg.com/profile_images/pic_normal.jpg",
            }
        }
        mock_oauth.get.return_value = mock_resp
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        info = TwitterService.fetch_user_info("token", "secret")

        assert info["account_name"] == "@janedoe"
        assert info["external_id"] == "123456"
        assert (
            info["profile_picture_url"]
            == "https://pbs.twimg.com/profile_images/pic.jpg"
        )
        assert info["username"] == "janedoe"
        assert info["is_premium"] is False

    def test_fetch_user_info_v2_premium(self, mocker):
        mock_oauth = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "id": "123456",
                "name": "Jane Doe",
                "username": "janedoe",
                "profile_image_url": "https://pbs.twimg.com/profile_images/pic_normal.jpg",
                "verified": True,
                "verified_type": "blue",
            }
        }
        mock_oauth.get.return_value = mock_resp
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        info = TwitterService.fetch_user_info("token", "secret")
        assert info["is_premium"] is True
        assert info["verified"] is True
        assert info["verified_type"] == "blue"

    def test_fetch_user_info_v1_fallback(self, mocker):
        mock_oauth = MagicMock()
        v2_resp = MagicMock()
        v2_resp.status_code = 403

        v1_resp = MagicMock()
        v1_resp.status_code = 200
        v1_resp.json.return_value = {
            "id_str": "654321",
            "name": "John Doe",
            "screen_name": "johndoe",
            "profile_image_url_https": "https://pbs.twimg.com/profile_images/pic_normal.png",
            "is_blue_verified": True,
        }
        mock_oauth.get.side_effect = [v2_resp, v1_resp]
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        info = TwitterService.fetch_user_info("token", "secret")

        assert info["account_name"] == "@johndoe"
        assert info["external_id"] == "654321"
        assert (
            info["profile_picture_url"]
            == "https://pbs.twimg.com/profile_images/pic.png"
        )
        assert info["is_premium"] is True

    def test_refresh_access_token_returns_none(self):
        assert TwitterService.refresh_access_token("any_refresh_token") is None


class TestTwitterServicePublishing:
    """Tests for publishing tweets and media uploads."""

    def test_post_tweet_text_only(self, mocker):
        mock_oauth = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "data": {"id": "999888777", "text": "Hello world!"}
        }
        mock_oauth.post.return_value = mock_resp
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        result = TwitterService.post_tweet("token", "secret", text="Hello world!")

        assert result["id"] == "999888777"
        assert result["text"] == "Hello world!"
        mock_oauth.post.assert_called_once()
        call_kwargs = mock_oauth.post.call_args[1]
        assert call_kwargs["json"] == {"text": "Hello world!"}

    def test_post_tweet_with_media_ids(self, mocker):
        mock_oauth = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "data": {"id": "111222333", "text": "Photo tweet"}
        }
        mock_oauth.post.return_value = mock_resp
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        result = TwitterService.post_tweet(
            "token", "secret", text="Photo tweet", media_ids=["media_1", "media_2"]
        )

        assert result["id"] == "111222333"
        call_kwargs = mock_oauth.post.call_args[1]
        assert call_kwargs["json"]["media"]["media_ids"] == ["media_1", "media_2"]

    def test_post_tweet_empty_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot publish an empty tweet"):
            TwitterService.post_tweet("token", "secret", text="", media_ids=None)

    def test_upload_photo_success(self, mocker):
        mock_oauth = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"media_id_string": "1234567890123"}
        mock_oauth.post.return_value = mock_resp
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        media_id = TwitterService.upload_photo("token", "secret", b"fake_image_bytes")
        assert media_id == "1234567890123"

    def test_upload_video_chunked_success(self, mocker):
        mock_oauth = MagicMock()

        # INIT response
        init_resp = MagicMock()
        init_resp.status_code = 202
        init_resp.json.return_value = {"media_id_string": "vid_media_999"}

        # APPEND response
        append_resp = MagicMock()
        append_resp.status_code = 204

        # FINALIZE response
        finalize_resp = MagicMock()
        finalize_resp.status_code = 201
        finalize_resp.json.return_value = {"media_id_string": "vid_media_999"}

        mock_oauth.post.side_effect = [init_resp, append_resp, finalize_resp]
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        media_id = TwitterService.upload_video("token", "secret", b"fake_video_content")
        assert media_id == "vid_media_999"

    def test_upload_video_streaming_url_success(self, mocker):
        mock_oauth = MagicMock()

        init_resp = MagicMock()
        init_resp.status_code = 202
        init_resp.json.return_value = {"media_id_string": "vid_media_stream_123"}

        append_resp = MagicMock()
        append_resp.status_code = 204

        finalize_resp = MagicMock()
        finalize_resp.status_code = 201
        finalize_resp.json.return_value = {"media_id_string": "vid_media_stream_123"}

        mock_oauth.post.side_effect = [init_resp, append_resp, finalize_resp]
        mocker.patch.object(
            TwitterService, "_get_oauth_session", return_value=mock_oauth
        )

        mock_stream_resp = MagicMock()
        mock_stream_resp.headers = {"Content-Length": "100"}
        mock_stream_resp.iter_bytes.return_value = [
            b"streamed_chunk_1",
            b"streamed_chunk_2",
        ]
        mock_stream_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.stream.return_value.__enter__.return_value = mock_stream_resp
        mock_client.stream.return_value.__exit__.return_value = None

        mocker.patch("httpx.Client", return_value=mock_client)

        media_id = TwitterService.upload_video(
            "token", "secret", "https://r2.example.com/video.mp4"
        )
        assert media_id == "vid_media_stream_123"
        assert mock_oauth.post.call_count == 3
