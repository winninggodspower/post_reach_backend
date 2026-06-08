import pytest

pytestmark = pytest.mark.django_db

FACEBOOK_AUTH_URL_PATH = "/api/social_accounts/facebook/auth-url/"
FACEBOOK_CONNECT_PATH = "/api/social_accounts/facebook/connect/"


class TestFacebookAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/facebook/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        """Should return an auth_url using the redirect URI from backend settings."""
        mock_auth_url = "https://www.facebook.com/v18.0/dialog/oauth?state=abc123&..."
        mocker.patch(
            "integrations.providers.facebook_service.FacebookService.generate_auth_url",
            return_value=mock_auth_url,
        )

        response = authenticated_client.get(FACEBOOK_AUTH_URL_PATH)

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["auth_url"] == mock_auth_url


class TestFacebookConnectEndpoint:
    """Tests for POST /api/social_accounts/facebook/connect/"""

    def test_connect_success(self, authenticated_client, mocker):
        """Should connect the account successfully with a valid authorization code."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_facebook",
            return_value=None,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            FACEBOOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["message"] == "Facebook account successfully connected"
        assert response.data["data"]["platform"] == "facebook"
        assert response.data["data"]["is_connected"] is True

    def test_connect_stores_page_info(self, authenticated_client, mocker, brand):
        """Should store account_name and external_id from the Facebook page."""
        mock_account = mocker.Mock()
        mock_account.account_name = "My Facebook Page"
        mock_account.external_id = "123456789"
        mock_account.platform = "facebook"
        mock_account.brand = brand

        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_facebook",
            return_value=mock_account,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
            "brand": brand.id,
        }

        response = authenticated_client.post(
            FACEBOOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

    def test_connect_missing_code(self, authenticated_client):
        """Should return 400 when code is missing."""
        payload = {}

        response = authenticated_client.post(
            FACEBOOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400

    def test_connect_missing_redirect_uri(self, authenticated_client):
        """Should return 400 when redirect_uri is missing."""
        payload = {"code": "valid_code"}

        response = authenticated_client.post(
            FACEBOOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400

    def test_connect_value_error(self, authenticated_client, mocker):
        """Should return 400 when connect_facebook raises a ValueError."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_facebook",
            side_effect=ValueError("Missing required Facebook permissions: pages_manage_posts"),
        )

        payload = {
            "code": "invalid_code",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            FACEBOOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False
