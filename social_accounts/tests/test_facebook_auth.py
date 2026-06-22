import pytest

from integrations.providers.facebook_service import FacebookService

pytestmark = pytest.mark.django_db

FACEBOOK_AUTH_URL_PATH = "/api/social_accounts/facebook/auth-url/"
FACEBOOK_CONNECT_PATH = "/api/social_accounts/facebook/connect/"
FACEBOOK_PAGES_PATH = "/api/social_accounts/facebook/pages/"


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


class TestFacebookPagesEndpoint:
    """Tests for POST /api/social_accounts/facebook/pages/"""

    FACEBOOK_PAGES_PATH = FACEBOOK_PAGES_PATH

    def test_pages_success(self, authenticated_client, mocker):
        """Should return list of pages with id, name, and picture_url."""
        mocker.patch.object(
            FacebookService,
            "exchange_code_for_token",
            return_value=("long_lived_token_789", 5184000),
        )
        mocker.patch.object(
            FacebookService,
            "get_facebook_pages",
            return_value=[
                {
                    "id": "123",
                    "name": "My Page",
                    "access_token": "page_token_1",
                    "picture_url": "https://example.com/pic1.jpg",
                },
                {
                    "id": "456",
                    "name": "Second Page",
                    "access_token": "page_token_2",
                    "picture_url": None,
                },
            ],
        )

        response = authenticated_client.post(
            FACEBOOK_PAGES_PATH,
            {"code": "auth_code", "redirect_uri": "https://example.com/callback"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        pages = response.data["data"]["pages"]
        assert len(pages) == 2
        assert pages[0] == {
            "id": "123",
            "name": "My Page",
            "picture_url": "https://example.com/pic1.jpg",
        }
        assert "access_token" not in pages[0]
        assert pages[1] == {
            "id": "456",
            "name": "Second Page",
            "picture_url": None,
        }
        assert "access_token" not in pages[1]

    def test_pages_missing_code(self, authenticated_client):
        """Should return 400 when code is missing."""
        response = authenticated_client.post(
            FACEBOOK_PAGES_PATH,
            {"redirect_uri": "https://example.com/callback"},
            format="json",
        )
        assert response.status_code == 400

    def test_pages_missing_redirect_uri(self, authenticated_client):
        """Should return 400 when redirect_uri is missing."""
        response = authenticated_client.post(
            FACEBOOK_PAGES_PATH,
            {"code": "auth_code"},
            format="json",
        )
        assert response.status_code == 400

    def test_pages_value_error(self, authenticated_client, mocker):
        """Should return 400 when exchange_code_for_token raises ValueError."""
        mocker.patch.object(
            FacebookService,
            "exchange_code_for_token",
            side_effect=ValueError("Invalid authorization code"),
        )

        response = authenticated_client.post(
            FACEBOOK_PAGES_PATH,
            {"code": "bad_code", "redirect_uri": "https://example.com/callback"},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False


class TestFacebookConnectEndpoint:
    """Tests for POST /api/social_accounts/facebook/connect/"""

    def test_connect_success_without_page_id(self, authenticated_client, mocker):
        """Should connect using the first page when no page_id is provided."""
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
        assert (
            response.data["data"]["message"]
            == "Facebook account successfully connected"
        )
        assert response.data["data"]["platform"] == "facebook"
        assert response.data["data"]["is_connected"] is True

    def test_connect_success_with_page_id(self, authenticated_client, mocker, brand):
        """Should connect using a specific page when page_id is provided."""
        mock_account = mocker.Mock()
        mock_account.account_name = "My Facebook Page"
        mock_account.external_id = "123"
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
            "page_id": "123",
        }

        response = authenticated_client.post(
            FACEBOOK_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

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
            side_effect=ValueError(
                "Missing required Facebook permissions: pages_manage_posts"
            ),
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
