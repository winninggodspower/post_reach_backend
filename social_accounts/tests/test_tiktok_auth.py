import pytest

pytestmark = pytest.mark.django_db

TIKTOK_AUTH_URL_PATH = "/api/social_accounts/tiktok/auth-url/"
TIKTOK_CONNECT_PATH = "/api/social_accounts/tiktok/connect/"


class TestTiktokAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/tiktok/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        """Should return an auth_url using the redirect URI from backend settings."""
        mock_auth_url = "https://www.tiktok.com/v2/auth/authorize/?state=abc123&code_challenge=xyz&..."
        mocker.patch(
            "integrations.providers.tiktok_service.TiktokService.generate_auth_url",
            return_value=mock_auth_url,
        )

        response = authenticated_client.get(TIKTOK_AUTH_URL_PATH)

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["auth_url"] == mock_auth_url

    def test_auth_url_unauthenticated(self, api_client):
        """Should return 401 when user is not authenticated."""
        response = api_client.get(TIKTOK_AUTH_URL_PATH)

        assert response.status_code == 401


class TestTiktokConnectEndpoint:
    """Tests for POST /api/social_accounts/tiktok/connect/"""

    def test_connect_success(self, authenticated_client, mocker):
        """Should connect the account successfully with a valid authorization code."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_tiktok",
            return_value=None,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            TIKTOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["message"] == "TikTok account successfully connected"
        assert response.data["data"]["platform"] == "tiktok"
        assert response.data["data"]["is_connected"] is True

    def test_connect_stores_account_info(self, authenticated_client, mocker, brand):
        """Should store account_name and external_id from TikTok user info."""
        mock_account = mocker.Mock()
        mock_account.account_name = "My TikTok Account"
        mock_account.external_id = "test_open_id_123"
        mock_account.platform = "tiktok"
        mock_account.brand = brand

        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_tiktok",
            return_value=mock_account,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
            "brand": brand.id,
        }

        response = authenticated_client.post(
            TIKTOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

    def test_connect_missing_code(self, authenticated_client):
        """Should return 400 when code is missing."""
        payload = {}

        response = authenticated_client.post(
            TIKTOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400

    def test_connect_missing_redirect_uri(self, authenticated_client):
        """Should return 400 when redirect_uri is missing."""
        payload = {"code": "valid_code"}

        response = authenticated_client.post(
            TIKTOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400

    def test_connect_value_error(self, authenticated_client, mocker):
        """Should return 400 when connect_tiktok raises a ValueError."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_tiktok",
            side_effect=ValueError("Code verifier not found. Please restart the OAuth flow."),
        )

        payload = {
            "code": "invalid_code",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            TIKTOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False

    def test_connect_unauthenticated(self, api_client):
        """Should return 401 when user is not authenticated."""
        payload = {
            "code": "valid_code",
            "redirect_uri": "https://example.com/callback",
        }

        response = api_client.post(
            TIKTOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 401
