from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from integrations.providers.instagram_service import InstagramService
from social_accounts.models import SocialAccount
from social_accounts.services.social_account_connection_service import (
    SocialAccountConnectionService,
)

pytestmark = pytest.mark.django_db

INSTAGRAM_AUTH_URL_PATH = "/api/social_accounts/instagram/auth-url/"
INSTAGRAM_CONNECT_PATH = "/api/social_accounts/instagram/connect/"


class TestInstagramAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/instagram/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        """Should return an auth_url using the redirect URI from settings."""
        mock_auth_url = "https://api.instagram.com/oauth/authorize?client_id=123&..."
        mocker.patch(
            "integrations.providers.instagram_service.InstagramService.generate_auth_url",
            return_value=mock_auth_url,
        )

        response = authenticated_client.get(INSTAGRAM_AUTH_URL_PATH)

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["auth_url"] == mock_auth_url

    def test_auth_url_unauthenticated(self, api_client):
        """Should return 401 when user is not authenticated."""
        response = api_client.get(INSTAGRAM_AUTH_URL_PATH)

        assert response.status_code == 401


class TestInstagramConnectEndpoint:
    """Tests for POST /api/social_accounts/instagram/connect/"""

    def test_connect_success(self, authenticated_client, mocker):
        """Should connect the account successfully with a valid auth code."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_instagram",
            return_value=None,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            INSTAGRAM_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert (
            response.data["data"]["message"]
            == "Instagram account successfully connected"
        )
        assert response.data["data"]["platform"] == "instagram"
        assert response.data["data"]["is_connected"] is True

    def test_connect_stores_user_info(self, authenticated_client, mocker, brand):
        """Should store account_name and external_id from Instagram profile."""
        mock_account = mocker.Mock()
        mock_account.account_name = "test_instagram_user"
        mock_account.external_id = "17841400797787220"
        mock_account.platform = "instagram"
        mock_account.brand = brand

        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_instagram",
            return_value=mock_account,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
            "brand": brand.id,
        }

        response = authenticated_client.post(
            INSTAGRAM_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

    def test_connect_missing_code(self, authenticated_client):
        """Should return 400 when code is missing."""
        payload = {"redirect_uri": "https://example.com/callback"}

        response = authenticated_client.post(
            INSTAGRAM_CONNECT_PATH,
            payload,
            format="json",
        )
        assert response.status_code == 400


class TestConnectInstagramService:
    """Tests for SocialAccountConnectionService.connect_instagram() logic."""

    def test_connect_instagram_fetches_and_saves_profile(self, mocker, user, brand):
        """Should fetch profile info and save external_id and account_name."""
        mocker.patch.object(
            InstagramService,
            "exchange_code_for_token",
            return_value=(
                {
                    "access_token": "long_lived_token_123",
                    "expires_in": 3600,
                    "user_id": "17841400797787220",
                },
                [],
            ),
        )

        mocker.patch.object(
            InstagramService,
            "fetch_user_info",
            return_value={
                "account_name": "test_instagram_user",
                "external_id": "17841400797787220",
            },
        )

        account, created = SocialAccountConnectionService.connect_instagram(
            user=user,
            brand=brand,
            auth_code="auth_code_123",
            redirect_uri="https://example.com/callback",
        )

        assert created is True
        assert account.platform == "instagram"
        assert account.account_name == "test_instagram_user"
        assert account.external_id == "17841400797787220"
        assert account.access_token == "long_lived_token_123"
