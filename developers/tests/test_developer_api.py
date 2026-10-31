from datetime import timedelta
import secrets
import pytest
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application
from rest_framework import status
from rest_framework.test import APIClient

from content.models import ContentPost
from users.models import Brand, User
from users.services.user_service import UserService

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_user():
    user = User.objects.create_user(
        email="developer_api_user@example.com",
        password="ValidPassword123!",
        first_name="Dev",
        last_name="Tester",
    )
    brand = Brand.objects.create(name="Dev Brand", user=user)
    UserService.set_active_brand(user, brand.id)
    return user


@pytest.fixture
def oauth_app(test_user):
    return Application.objects.create(
        user=test_user,
        name="Developer App",
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris="https://example.com/callback",
    )


def _create_token(user, app, scope):
    raw_token = f"test_{secrets.token_hex(16)}"
    token = AccessToken(
        user=user,
        application=app,
        token=raw_token,
        expires=timezone.now() + timedelta(hours=2),
        scope=scope,
    )
    token.save()
    return raw_token


class TestDeveloperBrandsAndAccounts:
    def test_list_brands_with_valid_scope(self, test_user, oauth_app):
        raw_token = _create_token(test_user, oauth_app, "accounts:read")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        url = reverse("v1-brand-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert len(response.data["data"]) >= 1

    def test_list_brands_insufficient_scope_fails(self, test_user, oauth_app):
        raw_token = _create_token(test_user, oauth_app, "posts:read")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        url = reverse("v1-brand-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_accounts_with_valid_scope(self, test_user, oauth_app):
        raw_token = _create_token(test_user, oauth_app, "accounts:read")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        url = reverse("v1-account-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "connected_accounts" in response.data["data"]


class TestDeveloperPosts:
    def test_create_post_with_write_scope_success(self, test_user, oauth_app, mocker):
        mocker.patch("content.tasks.wait_for_media_accessibility_and_publish.delay")
        mocker.patch("content.tasks.publish_platform_entry.delay")
        mocker.patch(
            "social_accounts.services.social_account_validation_service.SocialAccountValidationService.ensure_platforms_connected",
            return_value=True,
        )

        raw_token = _create_token(test_user, oauth_app, "posts:write accounts:read")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        url = reverse("v1-post-list-create")
        payload = {
            "caption": "Hello from PostGlee Developer API!",
            "platforms": ["twitter", "linkedin"],
        }
        response = client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True
        assert response.data["data"]["caption"] == "Hello from PostGlee Developer API!"

    def test_create_post_with_only_read_scope_rejected(self, test_user, oauth_app):
        raw_token = _create_token(test_user, oauth_app, "posts:read")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        url = reverse("v1-post-list-create")
        payload = {
            "caption": "Unauthorized post attempt",
            "platforms": ["twitter"],
        }
        response = client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_scheduled_posts(self, test_user, oauth_app):
        raw_token = _create_token(test_user, oauth_app, "posts:read")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        url = reverse("v1-post-list-create")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True

    def test_get_calendar_posts(self, test_user, oauth_app):
        raw_token = _create_token(test_user, oauth_app, "posts:read")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        url = reverse("v1-post-calendar")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True

    def test_get_update_delete_post(self, test_user, oauth_app):
        brand = UserService.get_active_brand(test_user)
        post = ContentPost.objects.create(
            user=test_user,
            brand=brand,
            caption="Initial post",
            content_type="text",
        )

        read_token = _create_token(test_user, oauth_app, "posts:read")
        write_token = _create_token(test_user, oauth_app, "posts:write")

        client = APIClient()

        # 1. GET with read_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {read_token}")
        url = reverse("v1-post-detail", kwargs={"post_id": str(post.id)})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["caption"] == "Initial post"

        # 2. PATCH with read_token should fail (requires posts:write)
        response = client.patch(url, data={"caption": "Hacked"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # 3. PATCH with write_token succeeds
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {write_token}")
        response = client.patch(url, data={"caption": "Updated caption"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["caption"] == "Updated caption"

        # 4. DELETE with write_token succeeds
        response = client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert not ContentPost.objects.filter(id=post.id).exists()


class TestDeveloperScopesDiscovery:
    def test_get_supported_scopes(self, test_user):
        client = APIClient()
        client.force_authenticate(user=test_user)

        url = reverse("developer-scopes")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        scope_keys = [s["scope"] for s in data]
        assert "accounts:read" in scope_keys
        assert "posts:read" in scope_keys
        assert "posts:write" in scope_keys

