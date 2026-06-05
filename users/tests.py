import pytest
from django.urls import reverse

from social_accounts.models import Brand
from users.models import User
from users.services import OnboardingService
from users.services import UserService


pytestmark = pytest.mark.django_db


def test_register_returns_user_and_tokens(api_client):
    response = api_client.post(
        reverse("register"),
        {
            "email": "new@example.com",
            "password": "StrongPass123!",
            "first_name": "New",
            "last_name": "User",
            "handle": "newuser",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["success"] is True
    assert response.data["data"]["user"]["email"] == "new@example.com"
    assert response.data["data"]["user"]["handle"] == "newuser"
    assert response.data["data"]["user"]["has_completed_onboarding"] is False
    assert response.data["data"]["tokens"]["access"]
    assert response.data["data"]["tokens"]["refresh"]


def test_register_creates_default_brand(api_client):
    response = api_client.post(
        reverse("register"),
        {
            "email": "brand-new@example.com",
            "password": "StrongPass123!",
            "first_name": "Brand",
            "last_name": "New",
            "handle": "brandnew",
        },
        format="json",
    )

    user = User.objects.get(email="brand-new@example.com")
    default_brand = Brand.objects.get(user=user, is_default=True)

    assert response.status_code == 201
    assert default_brand.name == "brandnew"


def test_sign_in_works_with_email(api_client, user):
    response = api_client.post(
        reverse("sign-in"),
        {"username": user.email, "password": "StrongPass123!"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["data"]["user"]["email"] == user.email
    assert response.data["data"]["tokens"]["access"]


def test_sign_in_works_with_handle(api_client, user):
    response = api_client.post(
        reverse("sign-in"),
        {"username": user.handle, "password": "StrongPass123!"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["data"]["user"]["handle"] == user.handle


def test_sign_in_rejects_invalid_credentials(api_client, user):
    response = api_client.post(
        reverse("sign-in"),
        {"username": user.email, "password": "wrong-password"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["success"] is False
    assert response.data["errors"]["detail"] == "Invalid username or password."


def test_google_sign_in_mocks_google_service(api_client, mocker):
    google_service = mocker.patch("users.views.GoogleAuthService")
    google_service.return_value.verify_and_get_user_info.return_value = {
        "email": "google@example.com",
        "first_name": "Google",
        "last_name": "User",
    }

    response = api_client.post(
        reverse("google-sign-in"),
        {
            "auth_code": "auth-code",
            "redirect_uri": "http://localhost:5173/oauth/google/callback",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["data"]["user"]["email"] == "google@example.com"
    assert response.data["data"]["tokens"]["access"]


def test_me_requires_authentication(api_client):
    response = api_client.get(reverse("current-user"))

    assert response.status_code == 401


def test_me_returns_current_user(authenticated_client, user):
    response = authenticated_client.get(reverse("current-user"))

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["data"]["email"] == user.email
    assert response.data["data"]["handle"] == user.handle
    assert response.data["data"]["has_completed_onboarding"] is False


def test_me_patch_updates_editable_user_fields(authenticated_client, user):
    response = authenticated_client.patch(
        reverse("current-user"),
        {
            "first_name": "Updated",
            "last_name": "Person",
            "handle": "updateduser",
            "email": "ignored@example.com",
        },
        format="json",
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert response.data["data"]["first_name"] == "Updated"
    assert response.data["data"]["last_name"] == "Person"
    assert response.data["data"]["handle"] == "updateduser"
    assert user.email != "ignored@example.com"


def test_onboarding_updates_user_and_default_brand(authenticated_client, user):
    response = authenticated_client.post(
        reverse("onboarding"),
        {
            "industry": "technology",
            "posting_frequency": "weekly",
            "primary_platform": "instagram",
            "role": "creator",
            "team_size": "just_me",
        },
        format="json",
    )

    user.refresh_from_db()
    brand = Brand.objects.get(user=user, is_default=True)

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["data"]["user"]["role"] == "creator"
    assert response.data["data"]["user"]["has_completed_onboarding"] is True
    assert response.data["data"]["brand"]["industry"] == "technology"
    assert user.role == "creator"
    assert brand.industry == "technology"
    assert brand.posting_frequency == "weekly"
    assert brand.primary_platform == "instagram"
    assert brand.team_size == "just_me"


def test_onboarding_rejects_unknown_choice(authenticated_client):
    response = authenticated_client.post(
        reverse("onboarding"),
        {
            "industry": "unknown",
            "posting_frequency": "weekly",
            "primary_platform": "instagram",
            "role": "creator",
            "team_size": "just_me",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "industry" in response.data


def test_register_with_password_creates_user():
    user = UserService.register_with_password(
        email="SERVICE@EXAMPLE.COM",
        password="StrongPass123!",
        first_name="Service",
        last_name="User",
        handle="serviceuser",
    )

    assert user.email == "SERVICE@example.com"
    assert user.check_password("StrongPass123!")
    assert user.handle == "serviceuser"


def test_register_with_password_rejects_duplicate_email(user):
    with pytest.raises(ValueError, match="already exists"):
        UserService.register_with_password(
            email=user.email,
            password="StrongPass123!",
        )


def test_register_with_password_rejects_duplicate_handle(user):
    with pytest.raises(ValueError, match="already exists"):
        UserService.register_with_password(
            email="other@example.com",
            password="StrongPass123!",
            handle=user.handle,
        )


def test_service_sign_in_with_email(user):
    signed_in_user = UserService.sign_in_with_password(
        username=user.email,
        password="StrongPass123!",
    )

    assert signed_in_user == user


def test_service_sign_in_with_handle(user):
    signed_in_user = UserService.sign_in_with_password(
        username=user.handle,
        password="StrongPass123!",
    )

    assert signed_in_user == user


def test_service_sign_in_rejects_invalid_password(user):
    with pytest.raises(ValueError, match="Invalid username or password"):
        UserService.sign_in_with_password(
            username=user.email,
            password="wrong-password",
        )


def test_get_or_create_social_user_does_not_duplicate_existing_user(user):
    social_user, created = UserService.get_or_create_social_user(
        email=user.email,
        first_name="Ignored",
        last_name="Name",
    )

    assert created is False
    assert social_user == user
    assert User.objects.filter(email=user.email).count() == 1


def test_get_or_create_social_user_creates_new_user():
    social_user, created = UserService.get_or_create_social_user(
        email="social@example.com",
        first_name="Social",
        last_name="User",
    )

    assert created is True
    assert social_user.email == "social@example.com"
    assert social_user.first_name == "Social"


def test_get_auth_tokens_returns_refresh_and_access(user):
    tokens = UserService.get_auth_tokens(user)

    assert tokens["refresh"]
    assert tokens["access"]


def test_complete_onboarding_updates_records(user):
    user, brand = OnboardingService.complete_onboarding(
        user=user,
        role="creator",
        industry="technology",
        posting_frequency="weekly",
        primary_platform="instagram",
        team_size="just_me",
    )

    user.refresh_from_db()
    brand.refresh_from_db()

    assert user.role == "creator"
    assert brand.industry == "technology"
    assert brand.posting_frequency == "weekly"
    assert brand.primary_platform == "instagram"
    assert brand.team_size == "just_me"
