import uuid

import pytest
from django.core.cache import cache

from integrations.providers.linkedin_service import LinkedinService
from utils.cache_keys import CacheKeys


class TestGenerateAuthUrl:
    """Tests for LinkedinService.generate_auth_url()"""

    def test_generate_auth_url_returns_url_with_required_params(self, user):
        """Should return a LinkedIn OAuth URL containing all required query parameters."""
        auth_url = LinkedinService.generate_auth_url(user_id=user.id)

        assert auth_url.startswith("https://www.linkedin.com/oauth/v2/authorization?")
        assert "client_id=" in auth_url
        assert "response_type=code" in auth_url
        assert "scope=" in auth_url
        assert "redirect_uri=" in auth_url
        assert "state=" in auth_url

    def test_generate_auth_url_includes_required_scopes(self, user):
        """Should include the required scopes in the URL."""
        auth_url = LinkedinService.generate_auth_url(user_id=user.id)

        assert "openid" in auth_url
        assert "profile" in auth_url
        assert "email" in auth_url
        assert "w_member_social" in auth_url

    def test_generate_auth_url_stores_state_in_cache(self, user):
        """Should store the OAuth state in cache for CSRF verification."""
        auth_url = LinkedinService.generate_auth_url(user_id=user.id)

        import urllib.parse

        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)
        state_from_url = params["state"][0]

        cached_state = cache.get(CacheKeys.linkedin_oauth_state(user.id))
        assert cached_state == state_from_url

    def test_generate_auth_url_uses_correct_redirect_uri(self, user):
        """Should use the LinkedIn redirect URI from settings."""
        from django.conf import settings

        auth_url = LinkedinService.generate_auth_url(user_id=user.id)

        import urllib.parse

        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)

        expected_redirect = settings.REDIRECT_URI["linkedin"]
        assert params["redirect_uri"][0] == expected_redirect

    def test_generate_auth_url_generates_unique_state_per_user(self, user):
        """Should generate different states for different users."""
        import urllib.parse

        # Create a second user
        from users.models import User

        user2 = User.objects.create_user(
            email="user2@example.com",
            password="StrongPass123!",
            first_name="Test2",
            last_name="User",
            handle="testuser2",
        )

        url1 = LinkedinService.generate_auth_url(user_id=user.id)
        url2 = LinkedinService.generate_auth_url(user_id=user2.id)

        state1 = urllib.parse.parse_qs(urllib.parse.urlparse(url1).query)["state"][0]
        state2 = urllib.parse.parse_qs(urllib.parse.urlparse(url2).query)["state"][0]

        assert state1 != state2


class TestExchangeCodeForToken:
    """Tests for LinkedinService.exchange_code_for_token()"""

    def test_exchange_code_for_token_success(self, mocker):
        """Should exchange code for token successfully."""
        mock_response = {
            "access_token": "linkedin_access_token_123",
            "expires_in": 5184000,  # 60 days
            "scope": "openid,profile,email,w_member_social",
        }
        mocker.patch.object(LinkedinService, "post", return_value=mock_response)

        result = LinkedinService.exchange_code_for_token(
            "auth_code_123",
            "https://example.com/callback",
        )

        assert result == mock_response

    def test_exchange_code_for_token_api_error(self, mocker):
        """Should raise ValueError when the token exchange API call fails."""
        from utils.http import APIError

        mocker.patch.object(
            LinkedinService, "post", side_effect=APIError("Token exchange failed")
        )

        with pytest.raises(ValueError, match="LinkedIn Auth Error"):
            LinkedinService.exchange_code_for_token(
                "bad_code", "https://example.com/callback"
            )

    def test_exchange_code_for_token_missing_access_token(self, mocker):
        """Should raise ValueError when response has no access_token."""
        mocker.patch.object(
            LinkedinService, "post", return_value={"error": "invalid_grant"}
        )

        with pytest.raises(ValueError, match="LinkedIn Auth Error"):
            LinkedinService.exchange_code_for_token(
                "bad_code", "https://example.com/callback"
            )

    def test_exchange_code_for_token_sends_correct_data(self, mocker):
        """Should send the correct data payload to /accessToken."""
        mock_post = mocker.patch.object(
            LinkedinService,
            "post",
            return_value={"access_token": "token"},
        )

        LinkedinService.exchange_code_for_token(
            "auth_code", "https://example.com/callback"
        )

        call_args = mock_post.call_args[0]
        call_kwargs = mock_post.call_args[1]
        assert call_args[0] == "/accessToken"
        assert call_kwargs["data"]["grant_type"] == "authorization_code"
        assert call_kwargs["data"]["code"] == "auth_code"
        assert call_kwargs["data"]["redirect_uri"] == "https://example.com/callback"
        assert "client_id" in call_kwargs["data"]
        assert "client_secret" in call_kwargs["data"]
        assert (
            call_kwargs["headers"]["Content-Type"]
            == "application/x-www-form-urlencoded"
        )


class TestFetchUserInfo:
    """Tests for LinkedinService.fetch_user_info()"""

    def test_fetch_user_info_success(self, mocker):
        """Should return account_name and external_id when user info is found."""
        from utils.http import BaseHTTPClient

        mock_get = mocker.patch.object(
            BaseHTTPClient,
            "get",
            return_value={
                "sub": "urn:li:person:abc123",
                "given_name": "John",
                "family_name": "Doe",
                "name": "John Doe",
            },
        )

        result = LinkedinService.fetch_user_info("valid_access_token")

        assert result == {
            "account_name": "John Doe",
            "external_id": "urn:li:person:abc123",
        }
        # Verify it used the correct endpoint
        assert mock_get.call_args[0][0] == "https://api.linkedin.com/v2/userinfo"
        # Verify Bearer token header
        assert (
            mock_get.call_args[1]["headers"]["Authorization"]
            == "Bearer valid_access_token"
        )

    def test_fetch_user_info_no_given_name(self, mocker):
        """Should handle missing given_name/family_name gracefully."""
        from utils.http import BaseHTTPClient

        mocker.patch.object(
            BaseHTTPClient,
            "get",
            return_value={
                "sub": "urn:li:person:def456",
                "name": "Jane Smith",
            },
        )

        result = LinkedinService.fetch_user_info("valid_token")

        assert result == {
            "account_name": "Jane Smith",
            "external_id": "urn:li:person:def456",
        }

    def test_fetch_user_info_missing_sub(self, mocker):
        """Should raise ValueError when response has no 'sub'."""
        from utils.http import BaseHTTPClient

        mocker.patch.object(
            BaseHTTPClient,
            "get",
            return_value={"name": "No ID User"},
        )

        with pytest.raises(ValueError, match="Failed to retrieve LinkedIn user ID"):
            LinkedinService.fetch_user_info("bad_token")

    def test_fetch_user_info_api_error(self, mocker):
        """Should raise ValueError when the API call fails."""
        from utils.http import APIError, BaseHTTPClient

        mocker.patch.object(
            BaseHTTPClient,
            "get",
            side_effect=APIError("API request failed"),
        )

        with pytest.raises(ValueError, match="Failed to fetch LinkedIn user info"):
            LinkedinService.fetch_user_info("bad_token")


class TestRefreshAccessToken:
    """Tests for LinkedinService.refresh_access_token()"""

    def test_refresh_access_token_returns_none(self):
        """Should return None as LinkedIn token refresh is not supported."""
        result = LinkedinService.refresh_access_token("some_refresh_token")
        assert result is None
