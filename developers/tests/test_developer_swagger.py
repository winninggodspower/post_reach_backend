import pytest
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User

pytestmark = pytest.mark.django_db


class TestDeveloperSwaggerDocs:
    def test_public_developer_swagger_json_accessible_without_auth(self):
        client = APIClient()
        response = client.get("/api/v1/swagger.json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["info"]["title"] == "PostGlee Developer API"
        assert data["info"]["version"] == "v1"
        assert data.get("basePath") == "/api/v1"

        # Check endpoints that MUST be present under basePath
        paths = data["paths"]
        assert "/brands/" in paths
        assert "/accounts/" in paths
        assert "/posts/" in paths
        assert "/posts/calendar/" in paths
        assert "/posts/{post_id}/" in paths

        # Check endpoints that MUST NOT be present in public developer docs
        assert "/auth/login/" not in paths
        assert "/api/auth/login/" not in paths
        assert "/subscriptions/" not in paths
        assert "/admin/analytics/" not in paths

    def test_public_developer_swagger_ui_html_accessible(self):
        client = APIClient()
        response = client.get("/api/v1/docs/")
        assert response.status_code == status.HTTP_200_OK
        assert "swagger-ui" in response.content.decode().lower()

    def test_public_developer_redoc_accessible(self):
        client = APIClient()
        response = client.get("/api/v1/redoc/")
        assert response.status_code == status.HTTP_200_OK

    def test_internal_swagger_accessible_during_local_debug(self, settings):
        settings.DEBUG = True
        client = APIClient()
        response = client.get("/swagger.json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["info"]["title"] == "PostGlee Internal API"

    def test_internal_swagger_protected_in_production_from_anonymous_users(self, settings):
        settings.DEBUG = False
        client = APIClient()
        response = client.get("/swagger.json")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_internal_swagger_protected_in_production_from_regular_users(self, settings):
        settings.DEBUG = False
        user = User.objects.create_user(
            email="regular@example.com",
            password="Password123!",
            is_staff=False,
        )
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/swagger.json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_internal_swagger_accessible_in_production_by_staff_admin(self, settings):
        settings.DEBUG = False
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
        )
        client = APIClient()
        client.force_authenticate(user=admin_user)
        response = client.get("/swagger.json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["info"]["title"] == "PostGlee Internal API"

