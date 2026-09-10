from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from integrations.providers.linkedin_service import LinkedinService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount
from social_accounts.services.social_account_connection_service import (
    SocialAccountConnectionService,
)

pytestmark = pytest.mark.django_db

LINKEDIN_AUTH_URL_PATH = "/api/social_accounts/linkedin/auth-url/"
LINKEDIN_CONNECT_PATH = "/api/social_accounts/linkedin/connect/"


class TestLinkedinAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/linkedin/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        """Should return an auth_url using the redirect URI from backend settings."""
        mock_auth_url = (
            "https://www.linkedin.com/oauth/v2/authorization?state=abc123&..."
        )
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
        assert (
            response.data["data"]["message"]
            == "LinkedIn account successfully connected"
        )
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


class TestLinkedinConnectionService:
    """Tests for SocialAccountConnectionService.connect_linkedin()."""

    @patch.object(SocialAccountConnectionService, "_sync_platform_profile_picture")
    def test_connect_linkedin_stores_refresh_token(
        self, mock_sync, mocker, user, brand
    ):
        """connect_linkedin should persist refresh_token when provided by token exchange."""
        mock_sync.return_value = "https://r2.example.com/pic.jpg"
        mocker.patch.object(
            LinkedinService,
            "exchange_code_for_token",
            return_value={
                "access_token": "li_access_token_123",
                "refresh_token": "li_refresh_token_456",
                "expires_in": 5184000,
                "scope": "openid profile email w_member_social",
            },
        )
        mocker.patch.object(
            LinkedinService,
            "fetch_user_info",
            return_value={
                "account_name": "Jane Doe",
                "external_id": "li_user_789",
                "profile_picture_url": "https://media.licdn.com/pic.jpg",
            },
        )

        account, created = SocialAccountConnectionService.connect_linkedin(
            user=user,
            brand=brand,
            code="auth_code_xyz",
            redirect_uri="https://example.com/callback",
        )

        assert created is True
        assert account.platform == "linkedin"
        assert account.access_token == "li_access_token_123"
        assert account.refresh_token == "li_refresh_token_456"
        assert account.account_name == "Jane Doe"
        assert account.external_id == "li_user_789"


class TestLinkedinSocialAccountRefresh:
    """Tests for SocialAccount.refresh_access_token() with LinkedIn."""

    def test_refresh_access_token_success(self, brand, mocker):
        """Should refresh access token and update refresh token if returned."""
        account = SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.LINKEDIN,
            account_name="Jane Doe",
            external_id="li_user_789",
            token_expires_at=timezone.now() - timedelta(minutes=5),
        )
        account.access_token = "old_access_token"
        account.refresh_token = "valid_refresh_token"
        account.save()

        mocker.patch.object(
            LinkedinService,
            "refresh_access_token",
            return_value={
                "access_token": "brand_new_access_token",
                "refresh_token": "rotated_refresh_token",
                "expires_in": 3600,
            },
        )

        result = account.refresh_access_token()

        assert result is True
        account.refresh_from_db()
        assert account.access_token == "brand_new_access_token"
        assert account.refresh_token == "rotated_refresh_token"
        assert account.token_expires_at > timezone.now()

    def test_refresh_access_token_without_refresh_token_fails(self, brand):
        """Should return False if refresh_token is missing on the account."""
        account = SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.LINKEDIN,
            account_name="Jane Doe",
            external_id="li_user_789",
            token_expires_at=timezone.now() - timedelta(minutes=5),
        )
        account.access_token = "old_access_token"
        account.save()

        assert account.refresh_token is None
        result = account.refresh_access_token()
        assert result is False

    def test_refresh_access_token_failure_returns_false(self, brand, mocker):
        """Should catch exception and return False if refresh API fails."""
        account = SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.LINKEDIN,
            account_name="Jane Doe",
            external_id="li_user_789",
            token_expires_at=timezone.now() - timedelta(minutes=5),
        )
        account.access_token = "old_access_token"
        account.refresh_token = "invalid_refresh_token"
        account.save()

        mocker.patch.object(
            LinkedinService,
            "refresh_access_token",
            side_effect=ValueError("LinkedIn Token Refresh Error: invalid_grant"),
        )

        result = account.refresh_access_token()
        assert result is False
