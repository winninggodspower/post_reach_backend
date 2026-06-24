import random
import string
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail

from utils.cache_keys import CacheKeys
from utils.custom_logger import CustomLogger, log_exceptions

User = get_user_model()

OTP_TTL = 600  # 10 minutes
RATE_LIMIT_TTL = 60  # 1 minute
TOKEN_TTL = 300  # 5 minutes
MAX_OTP_ATTEMPTS = 5


class PasswordResetService:
    """Service class for password reset flow using OTP verification."""

    @staticmethod
    def _generate_otp(length: int = 6) -> str:
        """Generate a cryptographically reasonable numeric OTP."""
        return "".join(random.choices(string.digits, k=length))

    @staticmethod
    def _generate_reset_token(length: int = 32) -> str:
        """Generate a secure random token for password reset authorization."""
        return "".join(
            random.choices(string.ascii_letters + string.digits, k=length)
        )

    @staticmethod
    @log_exceptions()
    def send_reset_otp(*, email: str) -> bool:
        """
        Generate and send a password reset OTP to the given email.

        Returns True always for security (don't reveal if email exists).
        Rate-limited to one request per 60 seconds per email.
        """
        normalized_email = User.objects.normalize_email(email)

        # Check rate limit
        rate_key = CacheKeys.pw_reset_rate_limit(normalized_email)
        if cache.get(rate_key):
            CustomLogger.info(
                "Password reset OTP rate-limited",
                extra={"email": normalized_email},
            )
            return True  # Silently succeed to not reveal existence

        # Set rate limit
        cache.set(rate_key, 1, RATE_LIMIT_TTL)

        # Check if user exists
        try:
            user = User.objects.get(email=normalized_email)
        except User.DoesNotExist:
            CustomLogger.info(
                "Password reset OTP requested for non-existent email",
                extra={"email": normalized_email},
            )
            return True  # Still return True for security

        # Generate and store OTP
        otp = PasswordResetService._generate_otp()
        otp_key = CacheKeys.pw_reset_otp(normalized_email)
        cache.set(otp_key, {"otp": otp, "attempts": 0}, OTP_TTL)

        # Send email via Django's send_mail
        subject = "Your Password Reset Code"
        message = (
            f"Hello {user.first_name or 'User'},\n\n"
            f"Your password reset code is: {otp}\n\n"
            f"This code is valid for 10 minutes. "
            f"Do not share this code with anyone.\n\n"
            f"If you did not request a password reset, please ignore this email."
        )
        html_message = (
            f"<p>Hello {user.first_name or 'User'},</p>"
            f"<p>Your password reset code is: "
            f"<strong style='font-size: 24px;'>{otp}</strong></p>"
            f"<p>This code is valid for <strong>10 minutes</strong>. "
            f"Do not share this code with anyone.</p>"
            f"<p>If you did not request a password reset, please ignore this email.</p>"
        )

        try:
            send_mail(
                subject=subject,
                message=message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[normalized_email],
                fail_silently=False,
            )
            CustomLogger.info(
                "Password reset OTP sent successfully",
                extra={"email": normalized_email},
            )
        except Exception as exc:
            CustomLogger.exception(
                "Failed to send password reset OTP email",
                extra={"email": normalized_email},
            )
            # Remove the OTP from cache since email failed
            cache.delete(otp_key)
            raise ValueError(
                "Failed to send the verification code. Please try again later."
            ) from exc

        return True

    @staticmethod
    @log_exceptions()
    def verify_reset_otp(*, email: str, otp: str) -> str:
        """
        Verify the OTP for the given email and return a reset token.

        Raises ValueError if OTP is invalid, expired, or max attempts exceeded.
        """
        normalized_email = User.objects.normalize_email(email)
        otp_key = CacheKeys.pw_reset_otp(normalized_email)
        otp_data = cache.get(otp_key)

        if otp_data is None:
            raise ValueError(
                "Verification code is invalid or has expired. "
                "Please request a new code."
            )

        # Check attempts
        if otp_data["attempts"] >= MAX_OTP_ATTEMPTS:
            cache.delete(otp_key)
            raise ValueError(
                "Too many incorrect attempts. Please request a new code."
            )

        # Increment attempts
        otp_data["attempts"] += 1
        cache.set(otp_key, otp_data, OTP_TTL)

        # Verify OTP
        if otp_data["otp"] != otp:
            remaining = MAX_OTP_ATTEMPTS - otp_data["attempts"]
            if remaining > 0:
                raise ValueError(
                    f"Incorrect verification code. {remaining} attempt(s) remaining."
                )
            else:
                cache.delete(otp_key)
                raise ValueError(
                    "Too many incorrect attempts. Please request a new code."
                )

        # OTP verified — generate reset token
        cache.delete(otp_key)  # OTP consumed
        reset_token = PasswordResetService._generate_reset_token()
        token_key = CacheKeys.pw_reset_token(reset_token)
        cache.set(token_key, normalized_email, TOKEN_TTL)

        CustomLogger.info(
            "Password reset OTP verified successfully",
            extra={"email": normalized_email},
        )
        return reset_token

    @staticmethod
    @log_exceptions()
    def reset_password(*, reset_token: str, new_password: str) -> None:
        """
        Reset the user's password using a valid reset token.

        Validates the new password against Django's password validators.
        Raises ValueError if token is invalid/expired or password fails validation.
        """
        token_key = CacheKeys.pw_reset_token(reset_token)
        email = cache.get(token_key)

        if email is None:
            raise ValueError(
                "Reset link is invalid or has expired. Please start the process again."
            )

        # Validate the new password
        try:
            validate_password(new_password)
        except DjangoValidationError as exc:
            raise ValueError(exc.messages) from exc

        # Fetch and update user
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            cache.delete(token_key)
            raise ValueError("User account not found.")

        user.set_password(new_password)
        user.save(update_fields=["password"])

        # Invalidate the token
        cache.delete(token_key)

        CustomLogger.info(
            "Password reset successful",
            extra={"email": email},
        )