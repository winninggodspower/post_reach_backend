from datetime import timedelta
import pytest
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, RefreshToken
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def developer_user():
    return User.objects.create_user(
        email="developer@example.com",
        password="ValidPassword123!",
        first_name="Dev",
        last_name="User",
    )


@pytest.fixture
def other_user():
    return User.objects.create_user(
        email="other@example.com",
        password="ValidPassword123!",
        first_name="Other",
        last_name="User",
    )


@pytest.fixture
def auth_client(developer_user):
    client = APIClient()
    client.force_authenticate(user=developer_user)
    return client


class TestDeveloperApplicationListCreate:
    def test_unauthenticated_request_rejected(self):
        client = APIClient()
        url = reverse("developer-application-list-create")
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_applications_empty(self, auth_client):
        url = reverse("developer-application-list-create")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["data"] == []

    def test_list_applications_scoped_to_user(self, auth_client, developer_user, other_user):
        # Create app for developer_user
        app1 = Application.objects.create(
            user=developer_user,
            name="My Dev App",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://example.com/oauth/callback",
        )
        # Create app for other_user
        Application.objects.create(
            user=other_user,
            name="Other App",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://other.com/oauth/callback",
        )

        url = reverse("developer-application-list-create")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert len(data) == 1
        assert data[0]["client_id"] == app1.client_id
        assert data[0]["name"] == "My Dev App"
        assert data[0]["redirect_uris_list"] == ["https://example.com/oauth/callback"]
        assert data[0]["client_secret"] is None

    def test_create_confidential_application_success(self, auth_client, developer_user):
        url = reverse("developer-application-list-create")
        payload = {
            "name": "Social Dashboard App",
            "client_type": "confidential",
            "redirect_uris": ["https://dashboard.example.com/callback", "https://localhost:3000/callback"],
        }
        response = auth_client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True

        data = response.data["data"]
        assert data["name"] == "Social Dashboard App"
        assert data["client_type"] == "confidential"
        assert data["authorization_grant_type"] == "authorization-code"
        assert len(data["redirect_uris_list"]) == 2
        assert "https://dashboard.example.com/callback" in data["redirect_uris_list"]

        # Raw client secret should be returned once on creation
        assert data["client_secret"] is not None
        assert len(data["client_secret"]) > 20

        # Check DB state: client secret must be hashed, not plaintext
        app = Application.objects.get(client_id=data["client_id"])
        assert app.user == developer_user
        assert app.client_secret.startswith("pbkdf2_sha256$")

    def test_create_public_application_success(self, auth_client):
        url = reverse("developer-application-list-create")
        payload = {
            "name": "Mobile Social App",
            "client_type": "public",
            "redirect_uris": "https://mobile.example.com/oauth/callback",
        }
        response = auth_client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.data["data"]
        assert data["client_type"] == "public"
        assert data["client_secret"] == ""

    def test_create_application_validation_error(self, auth_client):
        url = reverse("developer-application-list-create")
        # Missing redirect_uris
        response = auth_client.post(url, data={"name": "Bad App"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestDeveloperApplicationDetail:
    def test_get_application_detail_success(self, auth_client, developer_user):
        app = Application.objects.create(
            user=developer_user,
            name="Analytics App",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://analytics.example.com/callback",
        )
        url = reverse("developer-application-detail", kwargs={"client_id": app.client_id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["name"] == "Analytics App"
        assert data["client_id"] == app.client_id
        # Secret should NOT be returned on detail
        assert data["client_secret"] is None

    def test_get_application_other_user_forbidden(self, auth_client, other_user):
        app = Application.objects.create(
            user=other_user,
            name="Other Secret App",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://other.com/callback",
        )
        url = reverse("developer-application-detail", kwargs={"client_id": app.client_id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_application_success(self, auth_client, developer_user):
        app = Application.objects.create(
            user=developer_user,
            name="Initial Name",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://example.com/callback",
        )
        url = reverse("developer-application-detail", kwargs={"client_id": app.client_id})
        payload = {
            "name": "Updated Name",
            "redirect_uris": ["https://example.com/callback", "https://example.com/new-callback"],
        }
        response = auth_client.patch(url, data=payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["name"] == "Updated Name"
        assert len(data["redirect_uris_list"]) == 2

        app.refresh_from_db()
        assert app.name == "Updated Name"

    def test_delete_application_cascades_tokens(self, auth_client, developer_user):
        app = Application.objects.create(
            user=developer_user,
            name="App To Delete",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://example.com/callback",
        )
        # Issue an active token
        token = AccessToken.objects.create(
            user=developer_user,
            application=app,
            token="test-access-token",
            expires=timezone.now() + timedelta(hours=1),
            scope="accounts:read",
        )
        refresh = RefreshToken.objects.create(
            user=developer_user,
            application=app,
            token="test-refresh-token",
            access_token=token,
        )

        url = reverse("developer-application-detail", kwargs={"client_id": app.client_id})
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_200_OK

        assert not Application.objects.filter(client_id=app.client_id).exists()
        assert not AccessToken.objects.filter(id=token.id).exists()
        assert not RefreshToken.objects.filter(id=refresh.id).exists()


class TestDeveloperApplicationSecretRegeneration:
    def test_regenerate_secret_confidential_app(self, auth_client, developer_user):
        app = Application.objects.create(
            user=developer_user,
            name="Rotating App",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://example.com/callback",
        )
        initial_hash = app.client_secret

        url = reverse("developer-application-regenerate-secret", kwargs={"client_id": app.client_id})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]

        new_secret = data["client_secret"]
        assert new_secret is not None
        assert len(new_secret) > 20

        app.refresh_from_db()
        assert app.client_secret != initial_hash
        assert app.client_secret.startswith("pbkdf2_sha256$")

    def test_regenerate_secret_public_app_fails(self, auth_client, developer_user):
        app = Application.objects.create(
            user=developer_user,
            name="Public App",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://example.com/callback",
            client_secret="",
        )
        url = reverse("developer-application-regenerate-secret", kwargs={"client_id": app.client_id})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "public applications do not use client secrets" in response.data["message"].lower()

    def test_regenerate_secret_other_user_forbidden(self, auth_client, other_user):
        app = Application.objects.create(
            user=other_user,
            name="Other App",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://other.com/callback",
        )
        url = reverse("developer-application-regenerate-secret", kwargs={"client_id": app.client_id})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

