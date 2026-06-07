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
        """Should connect the account successfully with a valid short-lived token."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_facebook",
            return_value=None,
        )

        payload = {
            "short_lived_access_token": "valid_short_lived_token_123",
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

    def test_connect_missing_token(self, authenticated_client):
        """Should return 400 when short_lived_access_token is missing."""
        payload = {}

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
            side_effect=ValueError("Missing required Facebook permissions: publish_video"),
        )

        payload = {
            "short_lived_access_token": "invalid_token",
        }

        response = authenticated_client.post(
            FACEBOOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False