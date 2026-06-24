from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse

from users.services.password_reset_service import PasswordResetService
from utils.cache_keys import CacheKeys

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestPasswordResetService:
    """Unit tests for PasswordResetService."""

    def setup_method(self):
        cache.clear()

    def test_generate_otp_returns_six_digits(self):
        otp = PasswordResetService._generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_generate_reset_token_returns_32_chars(self):
        token = PasswordResetService._generate_reset_token()
        assert len(token) == 32
        assert token.isalnum()

    def test_cache_keys_are_consistent(self):
        assert CacheKeys.pw_reset_otp("a@b.com") == "pw_reset_otp:a@b.com"
        assert CacheKeys.pw_reset_rate_limit("a@b.com") == "pw_reset_rate_limit:a@b.com"
        assert CacheKeys.pw_reset_token("mytoken") == "pw_reset_token:mytoken"

    def test_send_reset_otp_returns_true_for_nonexistent_email(self):
        result = PasswordResetService.send_reset_otp(email="nobody@example.com")
        assert result is True

    @patch("users.services.password_reset_service.send_mail")
    def test_send_reset_otp_sends_email_for_existing_user(self, mock_send_mail, user):
        result = PasswordResetService.send_reset_otp(email=user.email)
        assert result is True
        mock_send_mail.assert_called_once()
        call_args = mock_send_mail.call_args
        assert user.email in call_args.kwargs["recipient_list"]

    @patch("users.services.password_reset_service.send_mail")
    def test_send_reset_otp_stores_otp_in_cache(self, mock_send_mail, user):
        PasswordResetService.send_reset_otp(email=user.email)
        otp_key = CacheKeys.pw_reset_otp(user.email)
        otp_data = cache.get(otp_key)
        assert otp_data is not None
        assert "otp" in otp_data
        assert len(otp_data["otp"]) == 6
        assert otp_data["attempts"] == 0

    @patch("users.services.password_reset_service.send_mail")
    def test_send_reset_otp_rate_limits(self, mock_send_mail, user):
        """Second call within 60s should not send another email."""
        PasswordResetService.send_reset_otp(email=user.email)
        mock_send_mail.reset_mock()

        PasswordResetService.send_reset_otp(email=user.email)
        mock_send_mail.assert_not_called()

    @patch("users.services.password_reset_service.send_mail")
    def test_verify_reset_otp_returns_token(self, mock_send_mail, user):
        PasswordResetService.send_reset_otp(email=user.email)
        otp_key = CacheKeys.pw_reset_otp(user.email)
        otp_data = cache.get(otp_key)

        reset_token = PasswordResetService.verify_reset_otp(
            email=user.email,
            otp=otp_data["otp"],
        )
        assert len(reset_token) == 32

        # Verify token is stored in cache
        token_key = CacheKeys.pw_reset_token(reset_token)
        assert cache.get(token_key) == user.email.lower()

    @patch("users.services.password_reset_service.send_mail")
    def test_verify_reset_otp_removes_otp_after_use(self, mock_send_mail, user):
        PasswordResetService.send_reset_otp(email=user.email)
        otp_key = CacheKeys.pw_reset_otp(user.email)
        otp_data = cache.get(otp_key)

        PasswordResetService.verify_reset_otp(
            email=user.email,
            otp=otp_data["otp"],
        )
        assert cache.get(otp_key) is None  # OTP consumed

    @patch("users.services.password_reset_service.send_mail")
    def test_verify_reset_otp_rejects_wrong_otp(self, mock_send_mail, user):
        PasswordResetService.send_reset_otp(email=user.email)

        with pytest.raises(ValueError, match="Incorrect verification code"):
            PasswordResetService.verify_reset_otp(
                email=user.email,
                otp="000000",
            )

    @patch("users.services.password_reset_service.send_mail")
    def test_verify_reset_otp_rejects_expired_otp(self, mock_send_mail, user):
        with pytest.raises(ValueError, match="expired"):
            PasswordResetService.verify_reset_otp(
                email=user.email,
                otp="123456",
            )

    @patch("users.services.password_reset_service.send_mail")
    def test_verify_reset_otp_blocks_after_max_attempts(self, mock_send_mail, user):
        PasswordResetService.send_reset_otp(email=user.email)
        otp_key = CacheKeys.pw_reset_otp(user.email)
        wrong_otp = "000000"

        # Use up all attempts (MAX_OTP_ATTEMPTS = 5)
        # The first 4 attempts give "remaining attempts", the 5th gives "too many"
        for i in range(4):
            try:
                PasswordResetService.verify_reset_otp(
                    email=user.email,
                    otp=wrong_otp,
                )
            except ValueError:
                pass

        # The 5th attempt should delete the OTP and say too many attempts
        with pytest.raises(ValueError, match="Too many incorrect attempts"):
            PasswordResetService.verify_reset_otp(
                email=user.email,
                otp=wrong_otp,
            )

        # OTP should be deleted after 5 failed attempts
        assert cache.get(otp_key) is None

        # A subsequent call should say expired since OTP was deleted
        with pytest.raises(ValueError, match="expired"):
            PasswordResetService.verify_reset_otp(
                email=user.email,
                otp=wrong_otp,
            )

    @patch("users.services.password_reset_service.send_mail")
    def test_reset_password_success(self, mock_send_mail, user):
        """Full flow: request OTP -> verify -> reset password."""
        PasswordResetService.send_reset_otp(email=user.email)
        otp_key = CacheKeys.pw_reset_otp(user.email)
        otp_data = cache.get(otp_key)

        reset_token = PasswordResetService.verify_reset_otp(
            email=user.email,
            otp=otp_data["otp"],
        )

        PasswordResetService.reset_password(
            reset_token=reset_token,
            new_password="NewStrongPass456!",
        )

        user.refresh_from_db()
        assert user.check_password("NewStrongPass456!")

    @patch("users.services.password_reset_service.send_mail")
    def test_reset_password_invalid_token(self, mock_send_mail, user):
        with pytest.raises(ValueError, match="invalid or has expired"):
            PasswordResetService.reset_password(
                reset_token="invalidtoken",
                new_password="NewStrongPass456!",
            )

    @patch("users.services.password_reset_service.send_mail")
    def test_reset_password_weak_password(self, mock_send_mail, user):
        PasswordResetService.send_reset_otp(email=user.email)
        otp_key = CacheKeys.pw_reset_otp(user.email)
        otp_data = cache.get(otp_key)

        reset_token = PasswordResetService.verify_reset_otp(
            email=user.email,
            otp=otp_data["otp"],
        )

        with pytest.raises(ValueError):
            PasswordResetService.reset_password(
                reset_token=reset_token,
                new_password="short",
            )


class TestPasswordResetAPI:
    """Integration tests for password reset endpoints."""

    def setup_method(self):
        cache.clear()

    @patch("users.services.password_reset_service.send_mail")
    def test_request_otp_returns_200_for_existing_user(
        self, mock_send_mail, api_client, user
    ):
        response = api_client.post(
            reverse("password-reset-request-otp"),
            {"email": user.email},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["success"] is True
        mock_send_mail.assert_called_once()

    def test_request_otp_returns_200_for_nonexistent_user(self, api_client):
        response = api_client.post(
            reverse("password-reset-request-otp"),
            {"email": "nobody@example.com"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["success"] is True

    def test_request_otp_validates_email(self, api_client):
        response = api_client.post(
            reverse("password-reset-request-otp"),
            {"email": "not-an-email"},
            format="json",
        )
        assert response.status_code == 400

    @patch("users.services.password_reset_service.send_mail")
    def test_full_reset_flow(self, mock_send_mail, api_client, user):
        """End-to-end test: request OTP -> verify -> reset password."""
        # 1. Request OTP
        response = api_client.post(
            reverse("password-reset-request-otp"),
            {"email": user.email},
            format="json",
        )
        assert response.status_code == 200
        mock_send_mail.assert_called_once()

        # Retrieve OTP from cache (simulates user checking email)
        otp_key = CacheKeys.pw_reset_otp(user.email)
        otp_data = cache.get(otp_key)

        # 2. Verify OTP
        response = api_client.post(
            reverse("password-reset-verify-otp"),
            {"email": user.email, "otp": otp_data["otp"]},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["success"] is True
        reset_token = response.data["data"]["reset_token"]
        assert reset_token is not None

        # 3. Reset password
        response = api_client.post(
            reverse("password-reset-reset"),
            {"reset_token": reset_token, "new_password": "NewStrongPass456!"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["success"] is True

        # Verify user can sign in with new password
        user.refresh_from_db()
        assert user.check_password("NewStrongPass456!")

    @patch("users.services.password_reset_service.send_mail")
    def test_verify_otp_rejects_wrong_code(self, mock_send_mail, api_client, user):
        api_client.post(
            reverse("password-reset-request-otp"),
            {"email": user.email},
            format="json",
        )

        response = api_client.post(
            reverse("password-reset-verify-otp"),
            {"email": user.email, "otp": "000000"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["success"] is False

    def test_reset_password_rejects_invalid_token(self, api_client):
        response = api_client.post(
            reverse("password-reset-reset"),
            {"reset_token": "invalidtoken", "new_password": "NewStrongPass456!"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["success"] is False