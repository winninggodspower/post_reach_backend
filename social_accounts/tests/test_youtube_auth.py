import uuid

import pytest

pytestmark = pytest.mark.django_db

YOUTUBE_AUTH_URL_PATH = "/api/social_accounts/youtube/auth-url/"
YOUTUBE_CONNECT_PATH = "/api/social_accounts/youtube/connect/"


class TestYoutubeAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/youtube/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        """Should return an auth_url when redirect_uri is provided."""
        mock_auth_url = "https://accounts.google.com/o/oauth2/auth?state=abc123&..."
        mocker.patch(
            "integrations.providers.youtube_service.YoutubeService.generate_auth_url",
            return_value=mock_auth_url,
        )

        response = authenticated_client.get(
            YOUTUBE_AUTH_URL_PATH,
            {"redirect_uri": "https://example.com/callback"},
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["auth_url"] == mock_auth_url

    def test_auth_url_missing_redirect_uri(self, authenticated_client):
        """Should return 400 when redirect_uri is missing."""
        response = authenticated_client.get(YOUTUBE_AUTH_URL_PATH)

        assert response.status_code == 400
        assert response.data["success"] is False


class TestYoutubeConnectEndpoint:
    """Tests for POST /api/social_accounts/youtube/connect/"""

    def test_connect_success(self, authenticated_client, mocker):
        """Should connect the account successfully with valid data."""
        mocker.patch(
            "integrations.providers.youtube_service.YoutubeService.connect_account",
            return_value=None,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
            "state": str(uuid.uuid4()),
        }

        response = authenticated_client.post(
            YOUTUBE_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["message"] == "YouTube account successfully connected"
        assert response.data["data"]["platform"] == "youtube"
        assert response.data["data"]["is_connected"] is True

    def test_connect_missing_code(self, authenticated_client):
        """Should return 400 when code is missing."""
        payload = {
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            YOUTUBE_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400

    def test_connect_permission_error(self, authenticated_client, mocker):
        """Should return 403 when user lacks permission for the brand."""
        mocker.patch(
            "integrations.providers.youtube_service.YoutubeService.connect_account",
            side_effect=PermissionError("You do not have permission to access this brand."),
        )

        payload = {
            "code": "valid_code",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            YOUTUBE_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 403
        assert response.data["success"] is False

    def test_connect_value_error(self, authenticated_client, mocker):
        """Should return 400 when YoutubeService raises a ValueError."""
        mocker.patch(
            "integrations.providers.youtube_service.YoutubeService.connect_account",
            side_effect=ValueError("No default brand found."),
        )

        payload = {
            "code": "valid_code",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            YOUTUBE_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False
