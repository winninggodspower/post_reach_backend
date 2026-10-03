import pytest

pytestmark = pytest.mark.django_db

TWITTER_AUTH_URL_PATH = "/api/social_accounts/twitter/auth-url/"
TWITTER_CONNECT_PATH = "/api/social_accounts/twitter/connect/"


class TestTwitterAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/twitter/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        mock_auth_url = "https://api.x.com/oauth/authorize?oauth_token=token123"
        mocker.patch(
            "integrations.providers.twitter_service.TwitterService.generate_auth_url",
            return_value=mock_auth_url,
        )

        response = authenticated_client.get(TWITTER_AUTH_URL_PATH)

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["auth_url"] == mock_auth_url

    def test_auth_url_unauthenticated(self, api_client):
        response = api_client.get(TWITTER_AUTH_URL_PATH)
        assert response.status_code == 401

    def test_auth_url_error_handling(self, authenticated_client, mocker):
        mocker.patch(
            "integrations.providers.twitter_service.TwitterService.generate_auth_url",
            side_effect=ValueError("Twitter API unreachable"),
        )

        response = authenticated_client.get(TWITTER_AUTH_URL_PATH)
        assert response.status_code == 500
        assert "Twitter API unreachable" in str(response.data)


class TestTwitterConnectEndpoint:
    """Tests for POST /api/social_accounts/twitter/connect/"""

    def test_connect_success(self, authenticated_client, mocker, brand):
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_twitter",
            return_value=None,
        )

        payload = {
            "oauth_token": "valid_oauth_token",
            "oauth_verifier": "valid_verifier",
            "brand": brand.id,
        }

        response = authenticated_client.post(
            TWITTER_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["message"] == "Twitter account successfully connected"
        assert response.data["data"]["platform"] == "twitter"
        assert response.data["data"]["is_connected"] is True

    def test_connect_missing_fields(self, authenticated_client):
        payload = {"oauth_token": "token_only"}
        response = authenticated_client.post(
            TWITTER_CONNECT_PATH,
            payload,
            format="json",
        )
        assert response.status_code == 400

    def test_connect_failure_raises_400(self, authenticated_client, mocker):
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_twitter",
            side_effect=ValueError("Invalid or expired authorization request"),
        )

        payload = {
            "oauth_token": "expired_token",
            "oauth_verifier": "verifier",
        }

        response = authenticated_client.post(
            TWITTER_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 400
        assert "Invalid or expired authorization request" in str(response.data)
