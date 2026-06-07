import uuid

import pytest
from django.core.cache import cache

from integrations.providers.facebook_service import FacebookService
from social_accounts.utils.cache_keys import facebook_oauth_state


class TestGenerateAuthUrl:
    """Tests for FacebookService.generate_auth_url()"""

    def test_generate_auth_url_returns_url_with_required_params(self, user):
        """Should return a Facebook OAuth URL containing all required query parameters."""
        auth_url = FacebookService.generate_auth_url(user_id=user.id)

        assert auth_url.startswith("https://www.facebook.com/v18.0/dialog/oauth?")
        assert "client_id=" in auth_url
        assert "redirect_uri=" in auth_url
        assert "state=" in auth_url
        assert "scope=" in auth_url
        assert "response_type=code" in auth_url
        assert "public_profile" in auth_url
        assert "publish_video" in auth_url

    def test_generate_auth_url_stores_state_in_cache(self, user):
        """Should store the OAuth state in cache for CSRF verification."""
        auth_url = FacebookService.generate_auth_url(user_id=user.id)

        # Extract state from the URL
        import urllib.parse
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)
        state_from_url = params["state"][0]

        # Verify state is stored in cache
        cached_state = cache.get(facebook_oauth_state(user.id))
        assert cached_state == state_from_url

    def test_generate_auth_url_uses_correct_redirect_uri(self, user):
        """Should use the Facebook redirect URI from settings."""
        from django.conf import settings

        auth_url = FacebookService.generate_auth_url(user_id=user.id)

        import urllib.parse
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)

        expected_redirect = settings.REDIRECT_URI["facebook"]
        assert params["redirect_uri"][0] == expected_redirect


class TestVerifyGrantedScope:
    """Tests for FacebookService.verify_granted_scope()"""

    def test_verify_granted_scope_all_permissions_granted(self, mocker):
        """Should return (True, set()) when all required permissions are granted."""
        mock_response = {
            "data": [
                {"permission": "public_profile", "status": "granted"},
                {"permission": "publish_video", "status": "granted"},
            ]
        }
        mocker.patch.object(FacebookService, "get", return_value=mock_response)

        is_valid, missing = FacebookService.verify_granted_scope("valid_token")

        assert is_valid is True
        assert missing == set()

    def test_verify_granted_scope_missing_permissions(self, mocker):
        """Should return (False, missing_set) when some permissions are not granted."""
        mock_response = {
            "data": [
                {"permission": "public_profile", "status": "granted"},
                {"permission": "publish_video", "status": "declined"},
            ]
        }
        mocker.patch.object(FacebookService, "get", return_value=mock_response)

        is_valid, missing = FacebookService.verify_granted_scope("token_with_missing_scope")

        assert is_valid is False
        assert missing == {"publish_video"}

    def test_verify_granted_scope_no_data_key(self, mocker):
        """Should raise ValueError when response has no 'data' key."""
        mocker.patch.object(FacebookService, "get", return_value={"error": "something went wrong"})

        with pytest.raises(ValueError, match="something went wrong"):
            FacebookService.verify_granted_scope("bad_token")


class TestExchangeShortLivedToken:
    """Tests for FacebookService.exchange_short_lived_token()"""

    def test_exchange_short_lived_token_success(self, mocker):
        """Should return long-lived token and expires_in when exchange succeeds."""
        mocker.patch.object(
            FacebookService,
            "verify_granted_scope",
            return_value=(True, set()),
        )
        mocker.patch.object(
            FacebookService,
            "get",
            return_value={"access_token": "long_lived_token_123", "expires_in": 5184000},
        )

        token, expires_in = FacebookService.exchange_short_lived_token("short_lived_token")

        assert token == "long_lived_token_123"
        assert expires_in == 5184000

    def test_exchange_short_lived_token_missing_permissions(self, mocker):
        """Should raise ValueError when required permissions are missing."""
        mocker.patch.object(
            FacebookService,
            "verify_granted_scope",
            return_value=(False, {"publish_video"}),
        )

        with pytest.raises(ValueError, match="Missing required Facebook permissions"):
            FacebookService.exchange_short_lived_token("insufficient_token")

    def test_exchange_short_lived_token_api_error(self, mocker):
        """Should raise ValueError when the token exchange API call fails."""
        from utils.http import APIError

        mocker.patch.object(
            FacebookService,
            "verify_granted_scope",
            return_value=(True, set()),
        )
        mocker.patch.object(
            FacebookService,
            "get",
            side_effect=APIError("API request failed"),
        )

        with pytest.raises(ValueError, match="API request failed"):
            FacebookService.exchange_short_lived_token("short_lived_token")

    def test_exchange_short_lived_token_no_access_token_in_response(self, mocker):
        """Should raise ValueError when response does not contain access_token."""
        mocker.patch.object(
            FacebookService,
            "verify_granted_scope",
            return_value=(True, set()),
        )
        mocker.patch.object(
            FacebookService,
            "get",
            return_value={"error": {"message": "Invalid token"}},
        )

        with pytest.raises(ValueError, match="Invalid token"):
            FacebookService.exchange_short_lived_token("bad_token")