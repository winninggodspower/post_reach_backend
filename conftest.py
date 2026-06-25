import pytest
from rest_framework.test import APIClient

from social_accounts.models import Brand
from users.models import User


def pytest_configure():
    from django.conf import settings

    # Override cache to use LocMemCache so tests don't require Redis
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-password-reset-cache",
        }
    }


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="user@example.com",
        password="StrongPass123!",
        first_name="Test",
        last_name="User",
        handle="testuser",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def brand(user):
    brand, _ = Brand.objects.get_or_create(
        user=user,
        is_default=True,
        defaults={"name": "Main Brand"},
    )
    return brand
