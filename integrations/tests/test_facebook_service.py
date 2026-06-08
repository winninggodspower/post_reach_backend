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
        assert "pages_show_list" in auth_url
        assert "pages_read_engagement" in auth_url
        assert "pages_manage_posts" in auth_url

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
                {"permission": "pages_show_list", "status": "granted"},
                {"permission": "pages_read_engagement", "status": "granted"},
                {"permission": "pages_manage_posts", "status": "granted"},
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
                {"permission": "pages_show_list", "status": "granted"},
                {"permission": "pages_read_engagement", "status": "granted"},
                {"permission": "pages_manage_posts", "status": "declined"},
            ]
        }
        mocker.patch.object(FacebookService, "get", return_value=mock_response)

        is_valid, missing = FacebookService.verify_granted_scope("token_with_missing_scope")

        assert is_valid is False
        assert missing == {"pages_manage_posts"}

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
            return_value=(False, {"pages_manage_posts"}),
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


class TestExchangeCodeForToken:
    """Tests for FacebookService.exchange_code_for_token()"""

    def test_exchange_code_for_token_success(self, mocker):
        """Should exchange code for short-lived token, then exchange for long-lived token."""
        # Mock the first get call (code → short-lived token)
        # and the second get call (short-lived → long-lived)
        mock_get = mocker.patch.object(
            FacebookService,
            "get",
            side_effect=[
                {"access_token": "short_lived_token_456"},  # code exchange response
                {"access_token": "long_lived_token_789", "expires_in": 5184000},  # short-lived exchange response
            ],
        )
        mocker.patch.object(
            FacebookService,
            "verify_granted_scope",
            return_value=(True, set()),
        )

        token, expires_in = FacebookService.exchange_code_for_token(
            "auth_code_123", "https://example.com/callback"
        )

        assert token == "long_lived_token_789"
        assert expires_in == 5184000
        assert mock_get.call_count == 2

    def test_exchange_code_for_token_api_error(self, mocker):
        """Should raise ValueError when the code exchange API call fails."""
        from utils.http import APIError

        mocker.patch.object(
            FacebookService,
            "get",
            side_effect=APIError("Code exchange failed"),
        )

        with pytest.raises(ValueError, match="Code exchange failed"):
            FacebookService.exchange_code_for_token("bad_code", "https://example.com/callback")

    def test_exchange_code_for_token_no_access_token(self, mocker):
        """Should raise ValueError when code exchange response has no access_token."""
        mocker.patch.object(
            FacebookService,
            "get",
            return_value={"error": {"message": "Invalid code"}},
        )

        with pytest.raises(ValueError, match="Invalid code"):
            FacebookService.exchange_code_for_token("bad_code", "https://example.com/callback")


class TestGetFacebookPages:
    """Tests for FacebookService.get_facebook_pages()"""

    def test_get_facebook_pages_success(self, mocker):
        """Should return a list of pages with id and name."""
        mocker.patch.object(
            FacebookService,
            "get",
            return_value={
                "data": [
                    {"id": "123", "name": "My Page", "access_token": "page_token_1"},
                    {"id": "456", "name": "Second Page", "access_token": "page_token_2"},
                ]
            },
        )

        pages = FacebookService.get_facebook_pages("valid_token")

        assert len(pages) == 2
        assert pages[0] == {"id": "123", "name": "My Page"}
        assert pages[1] == {"id": "456", "name": "Second Page"}

    def test_get_facebook_pages_no_pages(self, mocker):
        """Should raise ValueError when no pages are found."""
        mocker.patch.object(
            FacebookService,
            "get",
            return_value={"data": []},
        )

        with pytest.raises(ValueError, match="No Facebook pages found for this account"):
            FacebookService.get_facebook_pages("token_with_no_pages")

    def test_get_facebook_pages_api_error(self, mocker):
        """Should raise ValueError when the API call fails."""
        from utils.http import APIError

        mocker.patch.object(
            FacebookService,
            "get",
            side_effect=APIError("API request failed"),
        )

        with pytest.raises(ValueError, match="Failed to fetch Facebook pages"):
            FacebookService.get_facebook_pages("bad_token")
