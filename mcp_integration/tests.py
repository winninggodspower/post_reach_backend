import base64
import hashlib
import secrets
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, RefreshToken

from content.models import ContentPost, ContentPostPlatform
from mcp_integration.mcp import PostGleeMCPToolset
from mcp_integration.services import MCPContextService, OAuthConnectionService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount
from users.models import Brand, BrandMember, User
from users.services.user_service import UserService

pytestmark = pytest.mark.django_db


def _make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _issue_oauth_token(
    user,
    *,
    scope: str = "accounts:read posts:read posts:write",
    client_name: str = "Claude Desktop",
) -> tuple[Application, AccessToken, RefreshToken]:
    app = Application.objects.create(
        name=client_name,
        user=user,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris="http://localhost:6274/oauth/callback",
        registration_source=Application.RegistrationSource.DCR,
    )
    raw_access = secrets.token_urlsafe(32)
    access_token = AccessToken(
        user=user,
        application=app,
        expires=timezone.now() + timedelta(hours=1),
        scope=scope,
    )
    access_token.token = raw_access
    access_token.save()

    raw_refresh = secrets.token_urlsafe(32)
    refresh_token = RefreshToken(
        user=user,
        application=app,
        access_token=access_token,
    )
    refresh_token.token = raw_refresh
    refresh_token.save()
    return app, access_token, refresh_token


class TestSessionOnExistingAuth:
    def test_sign_in_establishes_django_session(self, api_client, user):
        response = api_client.post(
            reverse("sign-in"),
            {"username": user.email, "password": "StrongPass123!"},
            format="json",
        )
        assert response.status_code == 200
        assert "sessionid" in response.cookies
        assert api_client.session.get("_auth_user_id") == str(user.pk)

    def test_google_sign_in_establishes_django_session(self, api_client, mocker):
        google_service = mocker.patch("users.views.auth_view.GoogleAuthService")
        google_service.return_value.verify_and_get_user_info.return_value = {
            "email": "google-mcp@example.com",
            "first_name": "Google",
            "last_name": "MCP",
        }
        response = api_client.post(
            reverse("google-sign-in"),
            {"auth_code": "code123", "redirect_uri": "http://localhost:3000"},
            format="json",
        )
        assert response.status_code == 200
        assert "sessionid" in response.cookies
        assert api_client.session.get("_auth_user_id") is not None

    def test_sign_out_clears_session(self, api_client, user):
        api_client.post(
            reverse("sign-in"),
            {"username": user.email, "password": "StrongPass123!"},
            format="json",
        )
        assert api_client.session.get("_auth_user_id") == str(user.pk)

        out = api_client.post(reverse("sign-out"))
        assert out.status_code == 200
        assert api_client.session.get("_auth_user_id") is None


class TestMCPContextAndConnectionService:
    def test_require_scope_rejects_missing_scope(self, user, rf):
        _app, token, _rt = _issue_oauth_token(user, scope="accounts:read")
        req = rf.post("/mcp")
        req.user = user
        req.auth = token

        assert MCPContextService.require_scope(req, "accounts:read") == user
        with pytest.raises(PermissionError, match="posts:write"):
            MCPContextService.require_scope(req, "posts:write")

    def test_resolve_brand_checks_collaborator_membership(self, user, rf):
        other = User.objects.create_user(
            email="other@example.com",
            password="StrongPass123!",
            handle="otheruser",
        )
        other_brand = Brand.objects.filter(user=other).first()
        _app, token, _rt = _issue_oauth_token(user, scope="posts:read")
        req = rf.post("/mcp")
        req.user = user
        req.auth = token

        # Not a member yet -> rejected
        with pytest.raises(ValueError, match="Brand not found"):
            MCPContextService.resolve_brand(
                req, required_scope="posts:read", brand_id=str(other_brand.id)
            )

        # Added as member -> allowed
        BrandMember.objects.create(brand=other_brand, user=user, role="editor")
        _, resolved = MCPContextService.resolve_brand(
            req, required_scope="posts:read", brand_id=str(other_brand.id)
        )
        assert resolved.id == other_brand.id

    def test_list_and_revoke_connections_via_api(self, authenticated_client, user):
        app, _tok, _rt = _issue_oauth_token(
            user, scope="accounts:read posts:read", client_name="Cursor MCP"
        )

        list_resp = authenticated_client.get(reverse("oauth-connection-list"))
        assert list_resp.status_code == 200
        data = list_resp.data["data"]
        assert len(data) == 1
        assert data[0]["client_id"] == app.client_id
        assert data[0]["client_name"] == "Cursor MCP"
        assert set(data[0]["scopes"]) == {"accounts:read", "posts:read"}

        del_resp = authenticated_client.delete(
            reverse("oauth-connection-detail", args=[app.client_id])
        )
        assert del_resp.status_code == 200
        assert OAuthConnectionService.list_connections(user) == []


class TestMCPToolsetUnit:
    def _make_toolset(self, user, scope="accounts:read posts:read posts:write"):
        _app, token, _rt = _issue_oauth_token(user, scope=scope)
        req = type("Req", (), {"user": user, "auth": token})()
        return PostGleeMCPToolset(request=req)

    def test_list_brands_and_connected_accounts(self, user):
        brand = UserService.get_active_brand(user)
        account = SocialAccount(
            brand=brand,
            platform=PlatformChoices.LINKEDIN,
            account_name="Acme LinkedIn",
            external_id="li-123",
            token_expires_at=timezone.now() + timedelta(days=5),
        )
        account.access_token = "valid-access-token"
        account.save()
        toolset = self._make_toolset(user)

        brands = toolset.list_brands()
        assert len(brands) >= 1
        assert brands[0]["id"] == str(brand.id)

        accounts = toolset.list_connected_accounts()
        assert accounts["brand_id"] == str(brand.id)
        assert len(accounts["connected_accounts"]) == 1
        assert accounts["connected_accounts"][0]["platform"] == "linkedin"

    def test_create_update_get_delete_text_post(self, user, mocker):
        brand = UserService.get_active_brand(user)
        mocker.patch(
            "social_accounts.services.social_account_validation_service.SocialAccountValidationService.ensure_platforms_connected"
        )
        toolset = self._make_toolset(user)
        future_iso = (timezone.now() + timedelta(days=2)).isoformat()

        created = toolset.create_post(
            caption="Hello from MCP!",
            platforms=["linkedin"],
            scheduled_at=future_iso,
            brand_id=str(brand.id),
        )
        post_id = created["id"]
        assert created["caption"] == "Hello from MCP!"
        assert created["content_type"] == "text"

        fetched = toolset.get_post(post_id=post_id)
        assert fetched["id"] == post_id

        scheduled = toolset.list_scheduled_posts(brand_id=str(brand.id))
        assert any(p["id"] == post_id for p in scheduled)

        updated = toolset.update_post(
            post_id=post_id,
            caption="Updated caption from MCP",
        )
        assert updated["caption"] == "Updated caption from MCP"

        deleted = toolset.delete_post(post_id=post_id)
        assert deleted["deleted"] is True
        assert not ContentPost.objects.filter(id=post_id).exists()


class TestOAuthAndMCPEndToEnd:
    def test_unauthenticated_mcp_returns_401_with_protected_resource_metadata(self):
        client = Client()
        resp = client.post(
            "/mcp",
            data='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
            content_type="application/json",
        )
        assert resp.status_code == 401
        www_auth = resp.headers.get("WWW-Authenticate", "")
        assert "Bearer" in www_auth
        assert "/.well-known/oauth-protected-resource" in www_auth

    def test_well_known_discovery_endpoints(self):
        client = Client()
        pr_resp = client.get("/.well-known/oauth-protected-resource")
        assert pr_resp.status_code == 200
        pr_data = pr_resp.json()
        assert "authorization_servers" in pr_data
        assert set(pr_data["scopes_supported"]) == {
            "accounts:read",
            "posts:read",
            "posts:write",
        }

        as_resp = client.get("/.well-known/oauth-authorization-server")
        assert as_resp.status_code == 200
        as_data = as_resp.json()
        assert as_data["authorization_endpoint"].endswith("/oauth/authorize/")
        assert as_data["token_endpoint"].endswith("/oauth/token/")
        assert as_data["registration_endpoint"].endswith("/oauth/register/")
        assert "S256" in as_data["code_challenge_methods_supported"]

    def test_full_dcr_login_authorize_token_and_mcp_tool_call(self, user):
        client = Client()

        # 1. Dynamic Client Registration (RFC 7591)
        redirect_uri = "http://localhost:6274/oauth/callback"
        dcr_resp = client.post(
            "/oauth/register/",
            data={
                "client_name": "MCP Inspector",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
            content_type="application/json",
        )
        assert dcr_resp.status_code == 201, dcr_resp.content
        client_id = dcr_resp.json()["client_id"]

        # 2. Unauthenticated /oauth/authorize/ redirects to frontend LOGIN_URL with ?next=
        verifier, challenge = _make_pkce_pair()
        auth_params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "accounts:read posts:read",
            "state": "xyz123",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        anon_auth = client.get("/oauth/authorize/", auth_params)
        assert anon_auth.status_code == 302
        assert "/signin?next=" in anon_auth["Location"]

        # 3. User signs in via EXISTING /api/auth/sign-in/ -> sets session cookie
        login_resp = client.post(
            reverse("sign-in"),
            data={"username": user.email, "password": "StrongPass123!"},
            content_type="application/json",
        )
        assert login_resp.status_code == 200
        assert "sessionid" in login_resp.cookies

        # 4. Authenticated GET /oauth/authorize/ renders consent screen
        consent_get = client.get("/oauth/authorize/", auth_params)
        assert consent_get.status_code == 200
        assert b"MCP Inspector" in consent_get.content

        # 5. User approves consent form -> redirects with ?code=...&state=xyz123
        consent_post = client.post(
            "/oauth/authorize/",
            data={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "state": "xyz123",
                "scope": "accounts:read posts:read",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "allow": "Allow Access",
            },
        )
        assert consent_post.status_code == 302
        loc = consent_post["Location"]
        assert loc.startswith(redirect_uri)
        assert "code=" in loc
        assert "state=xyz123" in loc

        from urllib.parse import parse_qs, urlparse

        code = parse_qs(urlparse(loc).query)["code"][0]

        # 6. Exchange authorization code + PKCE verifier for OAuth tokens
        token_resp = client.post(
            "/oauth/token/",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        assert token_resp.status_code == 200, token_resp.content
        token_json = token_resp.json()
        access_token = token_json["access_token"]
        assert "refresh_token" in token_json

        # 7. Call /mcp tools/list and tools/call (list_brands) with Bearer token
        list_tools_resp = client.post(
            "/mcp",
            data={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            },
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert list_tools_resp.status_code == 200, list_tools_resp.content
        tools_payload = list_tools_resp.json()
        tool_names = {t["name"] for t in tools_payload["result"]["tools"]}
        assert {
            "list_brands",
            "list_connected_accounts",
            "list_scheduled_posts",
            "get_calendar",
            "get_post",
            "create_post",
            "update_post",
            "delete_post",
        }.issubset(tool_names)

        call_resp = client.post(
            "/mcp",
            data={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_brands", "arguments": {}},
            },
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert call_resp.status_code == 200
        call_result = call_resp.json()["result"]
        assert call_result["isError"] is False
