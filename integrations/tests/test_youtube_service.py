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
