import pytest

pytestmark = pytest.mark.django_db

LINKEDIN_AUTH_URL_PATH = "/api/social_accounts/linkedin/auth-url/"
LINKEDIN_CONNECT_PATH = "/api/social_accounts/linkedin/connect/"


class TestLinkedinAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/linkedin/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        """Should return an auth_url using the redirect URI from backend settings."""
        mock_auth_url = "https://www.linkedin.com/oauth/v2/authorization?state=abc123&..."
        mocker.patch(
            "integrations.providers.linkedin_service.LinkedinService.generate_auth_url",
            return_value=mock_auth_url,
        )

        response = authenticated_client.get(LINKEDIN_AUTH_URL_PATH)

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["auth_url"] == mock_auth_url

    def test_auth_url_unauthenticated(self, api_client):
        """Should return 401 when user is not authenticated."""
        response = api_client.get(LINKEDIN_AUTH_URL_PATH)

        assert response.status_code == 401


class TestLinkedinConnectEndpoint:
    """Tests for POST /api/social_accounts/linkedin/connect/"""

    def test_connect_success(self, authenticated_client, mocker):
        """Should connect the account successfully with a valid authorization code."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_linkedin",
            return_value=None,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            LINKEDIN_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["message"] == "LinkedIn account successfully connected"
        assert response.data["data"]["platform"] == "linkedin"
        assert response.data["data"]["is_connected"] is True

    def test_connect_stores_user_info(self, authenticated_client, mocker, brand):
        """Should store account_name and external_id from the LinkedIn profile."""
        mock_account = mocker.Mock()
        mock_account.account_name = "John Doe"
        mock_account.external_id = "urn:li:person:abc123"
        mock_account.platform = "linkedin"
        mock_account.brand = brand

        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_linkedin",
            return_value=mock_account,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
            "brand": brand.id,
        }

        response = authenticated_client.post(
            LINKEDIN_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

    def test_connect_missing_code(self, authenticated_client):
        """Should return 400 when code is missing."""
        payload = {}

        response = authenticated_client.post(
            LINKEDIN_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400

    def test_connect_missing_redirect_uri(self, authenticated_client):
        """Should return 400 when redirect_uri is missing."""
        payload = {"code": "valid_code"}

        response = authenticated_client.post(
            LINKEDIN_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400

    def test_connect_value_error(self, authenticated_client, mocker):
        """Should return 400 when connect_linkedin raises a ValueError."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_linkedin",
            side_effect=ValueError("LinkedIn Auth Error: invalid code"),
        )

        payload = {
            "code": "invalid_code",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            LINKEDIN_CONNECT_PATH,
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
            LINKEDIN_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 401
