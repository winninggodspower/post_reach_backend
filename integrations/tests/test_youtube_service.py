from datetime import datetime, timezone

import pytest
from google.oauth2.credentials import Credentials

from integrations.providers.youtube_service import YoutubeService


class TestFetchChannelInfo:
    """Tests for YoutubeService._fetch_channel_info()"""

    def test_fetch_channel_info_success(self, mocker):
        """Should return account_name and external_id when channel is found."""
        mock_credentials = mocker.Mock(spec=Credentials)
        mock_build = mocker.patch(
            "integrations.providers.youtube_service.googleapiclient.discovery.build"
        )

        mock_channels_list = mock_build.return_value.channels.return_value.list
        mock_execute = mock_channels_list.return_value.execute
        mock_execute.return_value = {
            "items": [
                {
                    "id": "UC_test_channel_id_123",
                    "snippet": {
                        "title": "My YouTube Channel",
                    },
                }
            ]
        }

        result = YoutubeService._fetch_channel_info(mock_credentials)

        assert result == {
            "account_name": "My YouTube Channel",
            "external_id": "UC_test_channel_id_123",
            "profile_picture_url": None,
        }
        mock_build.assert_called_once_with(
            "youtube", "v3", credentials=mock_credentials
        )
        mock_channels_list.assert_called_once_with(part="snippet", mine=True)

    def test_fetch_channel_info_no_channel(self, mocker):
        """Should raise ValueError when no YouTube channel is found."""
        mock_credentials = mocker.Mock(spec=Credentials)
        mocker.patch(
            "integrations.providers.youtube_service.googleapiclient.discovery.build"
        )

        mock_execute = mocker.patch(
            "integrations.providers.youtube_service.googleapiclient.discovery.build"
        ).return_value.channels.return_value.list.return_value.execute
        mock_execute.return_value = {"items": []}

        with pytest.raises(
            ValueError,
            match="No YouTube channel found for this account",
        ):
            YoutubeService._fetch_channel_info(mock_credentials)

    def test_fetch_channel_info_api_error(self, mocker):
        """Should raise ValueError when the API call fails."""
        mock_credentials = mocker.Mock(spec=Credentials)
        mocker.patch(
            "integrations.providers.youtube_service.googleapiclient.discovery.build",
            side_effect=Exception("API connection failed"),
        )

        with pytest.raises(
            ValueError,
            match="Failed to fetch YouTube channel information",
        ):
            YoutubeService._fetch_channel_info(mock_credentials)


class TestConnectAccount:
    """Tests for YoutubeService.connect_account()"""

    def test_connect_account_stores_channel_info(self, mocker, user, brand):
        """Should store account_name and external_id when connecting."""
        mock_credentials = mocker.Mock(spec=Credentials)
        mock_credentials.token = "access_token_123"
        mock_credentials.refresh_token = "refresh_token_456"
        mock_credentials.expiry = datetime(2026, 12, 31, tzinfo=timezone.utc)
        mock_credentials.scopes = [
            "openid",
            "https://www.googleapis.com/auth/youtube",
        ]

        mocker.patch.object(
            YoutubeService,
            "exchange_code_for_token",
            return_value=(mock_credentials, set()),
        )
        mocker.patch.object(
            YoutubeService,
            "_fetch_channel_info",
            return_value={
                "account_name": "My Channel",
                "external_id": "UC_test_id",
            },
        )

        account = YoutubeService.connect_account(
            user=user,
            auth_code="test_auth_code",
            brand=brand,
        )

        assert account.account_name == "My Channel"
        assert account.external_id == "UC_test_id"
        assert account.platform == "youtube"
        assert account.brand == brand

    def test_connect_account_invalid_state(self, mocker, user, brand):
        """Should raise ValueError when state is invalid."""
        from django.core.cache import cache

        from utils.cache_keys import CacheKeys

        cache.set(CacheKeys.youtube_oauth_state(user.id), "expected_state", 600)

        with pytest.raises(ValueError, match="Invalid state parameter"):
            YoutubeService.connect_account(
                user=user,
                auth_code="code",
                state="wrong_state",
                brand=brand,
            )

    def test_connect_account_missing_scopes(self, mocker, user, brand):
        """Should raise ValueError when required scopes are missing."""
        mock_credentials = mocker.Mock()
        mocker.patch.object(
            YoutubeService,
            "exchange_code_for_token",
            return_value=(mock_credentials, {"missing_scope"}),
        )

        with pytest.raises(ValueError, match="Missing required permissions"):
            YoutubeService.connect_account(
                user=user,
                auth_code="code",
                brand=brand,
            )


class TestPublishVideo:
    """Tests for YoutubeService.publish_video()"""

    def test_publish_video_bytes_success(self, mocker):
        mock_init_resp = mocker.MagicMock()
        mock_init_resp.status_code = 200
        mock_init_resp.headers = {
            "Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=yt_upload_999"
        }

        mock_chunk_resp = mocker.MagicMock()
        mock_chunk_resp.status_code = 200
        mock_chunk_resp.json.return_value = {"id": "yt_video_12345"}

        mock_client = mocker.MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_init_resp
        mock_client.put.return_value = mock_chunk_resp

        mocker.patch("httpx.Client", return_value=mock_client)

        result = YoutubeService.publish_video(
            access_token="test_yt_token",
            video_input=b"dummy_video_bytes",
            title="My Awesome Video",
            description="Testing YouTube Upload",
        )

        assert result == {"platform_post_id": "yt_video_12345"}
        mock_client.post.assert_called_once()
        mock_client.put.assert_called_once()

    def test_publish_video_streaming_url_success(self, mocker):
        mock_init_resp = mocker.MagicMock()
        mock_init_resp.status_code = 200
        mock_init_resp.headers = {
            "Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=yt_upload_888"
        }

        # Simulate 2 chunks: first returns 308 (intermediate), second returns 200 (final)
        mock_chunk_resp_1 = mocker.MagicMock()
        mock_chunk_resp_1.status_code = 308

        mock_chunk_resp_2 = mocker.MagicMock()
        mock_chunk_resp_2.status_code = 200
        mock_chunk_resp_2.json.return_value = {"id": "yt_video_stream_678"}

        mock_stream_resp = mocker.MagicMock()
        mock_stream_resp.headers = {"Content-Length": "10485760"}  # 10 MB
        chunk1 = b"x" * (5 * 1024 * 1024)
        chunk2 = b"y" * (5 * 1024 * 1024)
        mock_stream_resp.iter_bytes.return_value = [chunk1, chunk2]
        mock_stream_resp.raise_for_status = mocker.MagicMock()

        mock_client = mocker.MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_init_resp
        mock_client.put.side_effect = [mock_chunk_resp_1, mock_chunk_resp_2]
        mock_client.stream.return_value.__enter__.return_value = mock_stream_resp
        mock_client.stream.return_value.__exit__.return_value = None

        mocker.patch("httpx.Client", return_value=mock_client)

        result = YoutubeService.publish_video(
            access_token="test_yt_token",
            video_input="https://r2.postreach.xyz/videos/vid_10mb.mp4",
            title="Streaming 10MB Video",
        )

        assert result == {"platform_post_id": "yt_video_stream_678"}
        assert mock_client.put.call_count == 2

    def test_publish_video_init_failure_raises_value_error(self, mocker):
        mock_init_resp = mocker.MagicMock()
        mock_init_resp.status_code = 400
        mock_init_resp.text = "Invalid request"

        mock_client = mocker.MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_init_resp

        mocker.patch("httpx.Client", return_value=mock_client)

        with pytest.raises(ValueError, match="YouTube video upload INIT failed"):
            YoutubeService.publish_video(
                access_token="test_yt_token",
                video_input=b"dummy_bytes",
                title="Fail Video",
            )

    def test_publish_video_with_thumbnail_success(self, mocker):
        mock_init_resp = mocker.MagicMock()
        mock_init_resp.status_code = 200
        mock_init_resp.headers = {
            "Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=yt_thumb"
        }

        mock_chunk_resp = mocker.MagicMock()
        mock_chunk_resp.status_code = 200
        mock_chunk_resp.json.return_value = {"id": "yt_thumb_123"}

        mock_client = mocker.MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_init_resp
        mock_client.put.return_value = mock_chunk_resp

        mocker.patch("httpx.Client", return_value=mock_client)
        mock_upload_thumb = mocker.patch.object(YoutubeService, "_upload_thumbnail")

        result = YoutubeService.publish_video(
            access_token="test_yt_token",
            video_input=b"dummy_bytes",
            title="Thumbnail Video",
            thumbnail_bytes=b"fake_jpg_bytes",
        )

        assert result == {"platform_post_id": "yt_thumb_123"}
        mock_upload_thumb.assert_called_once_with(
            "test_yt_token", "yt_thumb_123", b"fake_jpg_bytes"
        )
