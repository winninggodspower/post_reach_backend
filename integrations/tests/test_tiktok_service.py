import hashlib
import uuid

import pytest
from django.core.cache import cache

from integrations.providers.tiktok_service import (
    TiktokService,
    _generate_code_challenge,
    _generate_code_verifier,
)
from social_accounts.utils.cache_keys import tiktok_code_verifier, tiktok_oauth_state


class TestPKCEHelpers:
    """Tests for PKCE helper functions."""

    def test_generate_code_verifier_length(self):
        """Should generate a code verifier of the specified length (default 128)."""
        verifier = _generate_code_verifier()
        assert len(verifier) == 128

    def test_generate_code_verifier_valid_characters(self):
        """Should only contain unreserved characters [A-Za-z0-9-._~]."""
        verifier = _generate_code_verifier()
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        assert all(c in valid_chars for c in verifier)

    def test_generate_code_verifier_randomness(self):
        """Should generate different values on each call."""
        verifier1 = _generate_code_verifier()
        verifier2 = _generate_code_verifier()
        assert verifier1 != verifier2

    def test_generate_code_challenge_is_sha256_hex(self):
        """Should produce a SHA256 hex digest (64 hex characters)."""
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        assert len(challenge) == 64
        assert all(c in "0123456789abcdef" for c in challenge)

    def test_generate_code_challenge_deterministic(self):
        """Should produce the same challenge for the same verifier."""
        verifier = _generate_code_verifier()
        challenge1 = _generate_code_challenge(verifier)
        challenge2 = _generate_code_challenge(verifier)
        assert challenge1 == challenge2

    def test_generate_code_challenge_matches_manual_sha256(self):
        """Should match a manually computed SHA256 hex digest."""
        verifier = "test-verifier-123"
        expected = hashlib.sha256(verifier.encode("ascii")).hexdigest()
        assert _generate_code_challenge(verifier) == expected


class TestGenerateAuthUrl:
    """Tests for TiktokService.generate_auth_url()"""

    def test_generate_auth_url_returns_url_with_required_params(self, user):
        """Should return a TikTok OAuth URL containing all required query parameters."""
        auth_url = TiktokService.generate_auth_url(user_id=user.id)

        assert auth_url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
        assert "client_key=" in auth_url
        assert "response_type=code" in auth_url
        assert "scope=" in auth_url
        assert "redirect_uri=" in auth_url
        assert "state=" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url

    def test_generate_auth_url_includes_required_scopes(self, user):
        """Should include the required scopes in the URL."""
        auth_url = TiktokService.generate_auth_url(user_id=user.id)

        assert "user.info.basic" in auth_url
        assert "video.publish" in auth_url
        assert "video.upload" in auth_url

    def test_generate_auth_url_stores_state_in_cache(self, user):
        """Should store the OAuth state in cache for CSRF verification."""
        auth_url = TiktokService.generate_auth_url(user_id=user.id)

        import urllib.parse
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)
        state_from_url = params["state"][0]

        cached_state = cache.get(tiktok_oauth_state(user.id))
        assert cached_state == state_from_url

    def test_generate_auth_url_stores_code_verifier_in_cache(self, user):
        """Should store the PKCE code verifier in cache for token exchange."""
        TiktokService.generate_auth_url(user_id=user.id)

        cached_verifier = cache.get(tiktok_code_verifier(user.id))
        assert cached_verifier is not None
        assert len(cached_verifier) == 128

    def test_generate_auth_url_code_challenge_matches_verifier(self, user):
        """Should generate a code_challenge that matches the cached code_verifier."""
        auth_url = TiktokService.generate_auth_url(user_id=user.id)

        import urllib.parse
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)
        code_challenge_from_url = params["code_challenge"][0]

        cached_verifier = cache.get(tiktok_code_verifier(user.id))
        expected_challenge = _generate_code_challenge(cached_verifier)
        assert code_challenge_from_url == expected_challenge

    def test_generate_auth_url_uses_correct_redirect_uri(self, user):
        """Should use the TikTok redirect URI from settings."""
        from django.conf import settings

        auth_url = TiktokService.generate_auth_url(user_id=user.id)

        import urllib.parse
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)

        expected_redirect = settings.REDIRECT_URI["tiktok"]
        assert params["redirect_uri"][0] == expected_redirect


class TestExchangeCodeForToken:
    """Tests for TiktokService.exchange_code_for_token()"""

    def test_exchange_code_for_token_success(self, mocker, user):
        """Should exchange code for token successfully with code_verifier from cache."""
        mock_response = {
            "access_token": "tiktok_access_token_123",
            "refresh_token": "tiktok_refresh_token_456",
            "expires_in": 86400,
            "scope": "user.info.basic,video.publish",
        }
        mocker.patch.object(TiktokService, "post", return_value=mock_response)

        # Set up the code_verifier in cache
        verifier = _generate_code_verifier()
        cache.set(tiktok_code_verifier(user.id), verifier, 600)

        result = TiktokService.exchange_code_for_token("auth_code_123", user.id)

        assert result == mock_response
        # Verify code_verifier is cleaned up after use
        assert cache.get(tiktok_code_verifier(user.id)) is None

    def test_exchange_code_for_token_missing_verifier(self, user):
        """Should raise ValueError when no code_verifier is in cache."""
        cache.delete(tiktok_code_verifier(user.id))

        with pytest.raises(ValueError, match="Code verifier not found"):
            TiktokService.exchange_code_for_token("auth_code_123", user.id)

    def test_exchange_code_for_token_api_error(self, mocker, user):
        """Should raise ValueError when the token exchange API call fails."""
        from utils.http import APIError

        mocker.patch.object(TiktokService, "post", side_effect=APIError("Token exchange failed"))

        verifier = _generate_code_verifier()
        cache.set(tiktok_code_verifier(user.id), verifier, 600)

        with pytest.raises(ValueError, match="Token exchange failed"):
            TiktokService.exchange_code_for_token("bad_code", user.id)

    def test_exchange_code_for_token_empty_response(self, mocker, user):
        """Should raise ValueError when response is empty."""
        mocker.patch.object(TiktokService, "post", return_value=None)

        verifier = _generate_code_verifier()
        cache.set(tiktok_code_verifier(user.id), verifier, 600)

        with pytest.raises(ValueError, match="Error while fetching access token from TikTok"):
            TiktokService.exchange_code_for_token("bad_code", user.id)

    def test_exchange_code_for_token_sends_correct_data(self, mocker, user):
        """Should send the correct data payload to /v2/oauth/token/."""
        mock_post = mocker.patch.object(
            TiktokService,
            "post",
            return_value={"access_token": "token"},
        )

        verifier = _generate_code_verifier()
        cache.set(tiktok_code_verifier(user.id), verifier, 600)

        TiktokService.exchange_code_for_token("auth_code", user.id)

        # Verify the correct endpoint and data payload
        call_args = mock_post.call_args[0]
        call_kwargs = mock_post.call_args[1]
        assert call_args[0] == "/v2/oauth/token/"
        assert call_kwargs["data"]["code_verifier"] == verifier
        assert call_kwargs["data"]["grant_type"] == "authorization_code"
        assert call_kwargs["data"]["code"] == "auth_code"
        assert "redirect_uri" in call_kwargs["data"]


class TestFetchUserInfo:
    """Tests for TiktokService.fetch_user_info()"""

    def test_fetch_user_info_success(self, mocker):
        """Should return account_name and external_id when user info is found."""
        from utils.http import BaseHTTPClient

        mock_get = mocker.patch.object(
            BaseHTTPClient,
            "get",
            return_value={
                "data": {
                    "open_id": "test_open_id_123",
                    "display_name": "My TikTok Account",
                    "username": "mytiktok",
                }
            },
        )

        result = TiktokService.fetch_user_info("valid_access_token")

        assert result == {
            "account_name": "My TikTok Account",
            "external_id": "test_open_id_123",
        }
        # Verify it used the correct base URL
        assert mock_get.call_args[0][0] == "/oauth/userinfo/"

    def test_fetch_user_info_falls_back_to_username(self, mocker):
        """Should fall back to username when display_name is empty."""
        from utils.http import BaseHTTPClient

        mocker.patch.object(
            BaseHTTPClient,
            "get",
            return_value={
                "data": {
                    "open_id": "test_open_id_456",
                    "display_name": "",
                    "username": "fallback_user",
                }
            },
        )

        result = TiktokService.fetch_user_info("valid_token")

        assert result == {
            "account_name": "fallback_user",
            "external_id": "test_open_id_456",
        }

    def test_fetch_user_info_no_data_key(self, mocker):
        """Should raise ValueError when response has no 'data' key."""
        from utils.http import BaseHTTPClient

        mocker.patch.object(
            BaseHTTPClient,
            "get",
            return_value={"error": "something went wrong"},
        )

        with pytest.raises(ValueError, match="Unable to retrieve TikTok user information"):
            TiktokService.fetch_user_info("bad_token")

    def test_fetch_user_info_api_error(self, mocker):
        """Should raise ValueError when the API call fails."""
        from utils.http import APIError, BaseHTTPClient

        mocker.patch.object(
            BaseHTTPClient,
            "get",
            side_effect=APIError("API request failed"),
        )

        with pytest.raises(ValueError, match="Failed to fetch TikTok user info"):
            TiktokService.fetch_user_info("bad_token")


class TestRefreshAccessToken:
    """Tests for TiktokService.refresh_access_token()"""

    def test_refresh_access_token_success(self, mocker):
        """Should return new token data when refresh succeeds."""
        mock_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 86400,
        }
        mocker.patch.object(TiktokService, "post", return_value=mock_response)

        result = TiktokService.refresh_access_token("old_refresh_token")

        assert result == mock_response

    def test_refresh_access_token_api_error(self, mocker):
        """Should raise ValueError when the refresh API call fails."""
        from utils.http import APIError

        mocker.patch.object(TiktokService, "post", side_effect=APIError("Refresh failed"))

        with pytest.raises(ValueError, match="Refresh failed"):
            TiktokService.refresh_access_token("bad_token")

    def test_refresh_access_token_empty_response(self, mocker):
        """Should raise ValueError when response is empty."""
        mocker.patch.object(TiktokService, "post", return_value=None)

        with pytest.raises(ValueError, match="Error while refreshing access token from TikTok"):
            TiktokService.refresh_access_token("bad_token")

    def test_refresh_access_token_sends_correct_data(self, mocker):
        """Should send the correct data payload to /v2/oauth/token/."""
        mock_post = mocker.patch.object(
            TiktokService,
            "post",
            return_value={"access_token": "new_token"},
        )

        TiktokService.refresh_access_token("old_refresh_token")

        call_args = mock_post.call_args[0]
        call_kwargs = mock_post.call_args[1]
        assert call_args[0] == "/v2/oauth/token/"
        assert call_kwargs["data"]["grant_type"] == "refresh_token"
        assert call_kwargs["data"]["refresh_token"] == "old_refresh_token"
        assert "client_secret" in call_kwargs["data"]
