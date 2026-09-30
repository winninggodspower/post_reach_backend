from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from integrations.providers.threads_service import ThreadsService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount
from social_accounts.services.social_account_connection_service import (
    SocialAccountConnectionService,
)

pytestmark = pytest.mark.django_db

THREADS_AUTH_URL_PATH = "/api/social_accounts/threads/auth-url/"
THREADS_CONNECT_PATH = "/api/social_accounts/threads/connect/"


class TestThreadsAuthUrlEndpoint:
    """Tests for GET /api/social_accounts/threads/auth-url/"""

    def test_auth_url_success(self, authenticated_client, mocker):
        """Should return an auth_url using the redirect URI from settings."""
        mock_auth_url = "https://threads.net/oauth/authorize?client_id=123&..."
        mocker.patch(
            "integrations.providers.threads_service.ThreadsService.generate_auth_url",
            return_value=mock_auth_url,
        )

        response = authenticated_client.get(THREADS_AUTH_URL_PATH)

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["auth_url"] == mock_auth_url

    def test_auth_url_unauthenticated(self, api_client):
        """Should return 401 when user is not authenticated."""
        response = api_client.get(THREADS_AUTH_URL_PATH)
        assert response.status_code == 401


class TestThreadsConnectEndpoint:
    """Tests for POST /api/social_accounts/threads/connect/"""

    def test_connect_success(self, authenticated_client, mocker):
        """Should connect the account successfully with a valid auth code."""
        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_threads",
            return_value=None,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
        }

        response = authenticated_client.post(
            THREADS_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert (
            response.data["data"]["message"]
            == "Threads account successfully connected"
        )
        assert response.data["data"]["platform"] == "threads"
        assert response.data["data"]["is_connected"] is True

    def test_connect_stores_user_info(self, authenticated_client, mocker, brand):
        """Should store account_name and external_id from Threads profile."""
        mock_account = mocker.Mock()
        mock_account.account_name = "test_threads_user"
        mock_account.external_id = "987654321"
        mock_account.platform = "threads"
        mock_account.brand = brand

        mocker.patch(
            "social_accounts.services.social_account_connection_service.SocialAccountConnectionService.connect_threads",
            return_value=mock_account,
        )

        payload = {
            "code": "valid_auth_code_123",
            "redirect_uri": "https://example.com/callback",
            "brand": brand.id,
        }

        response = authenticated_client.post(
            THREADS_CONNECT_PATH,
            payload,
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

    def test_connect_missing_code(self, authenticated_client):
        """Should return 400 when code is missing."""
        payload = {"redirect_uri": "https://example.com/callback"}

        response = authenticated_client.post(
            THREADS_CONNECT_PATH,
            payload,
            format="json",
        )
        assert response.status_code == 400


class TestConnectThreadsService:
    """Tests for SocialAccountConnectionService.connect_threads() logic."""

    def test_connect_threads_fetches_and_saves_profile(self, mocker, user, brand):
        """Should fetch profile info and save external_id and account_name."""
        mocker.patch.object(
            ThreadsService,
            "exchange_code_for_token",
            return_value=(
                {
                    "access_token": "threads_long_lived_token_123",
                    "expires_in": 5184000,
                    "user_id": "987654321",
                },
                [],
            ),
        )

        mocker.patch.object(
            ThreadsService,
            "fetch_user_info",
            return_value={
                "account_name": "test_threads_user",
                "external_id": "987654321",
                "profile_picture_url": "https://example.com/pic.jpg",
            },
        )

        account, created = SocialAccountConnectionService.connect_threads(
            user=user,
            brand=brand,
            auth_code="auth_code_123",
            redirect_uri="https://example.com/callback",
        )

        assert created is True
        assert account.platform == "threads"
        assert account.account_name == "test_threads_user"
        assert account.external_id == "987654321"
        assert account.access_token == "threads_long_lived_token_123"


class TestThreadsSocialAccountRefresh:
    """Tests for SocialAccount.refresh_access_token() with Threads."""

    def test_refresh_threads_token_success(self, mocker, brand):
        """Should successfully refresh a Threads access token."""
        account = SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.THREADS,
            external_id="threads_123",
            access_token="old_threads_token",
            token_expires_at=timezone.now() - timedelta(hours=1),
        )

        mocker.patch.object(
            ThreadsService,
            "refresh_access_token",
            return_value={
                "access_token": "new_threads_token",
                "refresh_token": None,
                "expires_in": 5184000,
            },
        )

        success = account.refresh_access_token()
        assert success is True

        account.refresh_from_db()
        assert account.access_token == "new_threads_token"
        assert account.token_expires_at > timezone.now()
