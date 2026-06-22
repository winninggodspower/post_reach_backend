from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework_simplejwt.tokens import RefreshToken

from utils.custom_logger import CustomLogger, log_exceptions

User = get_user_model()


class UserService:
    @staticmethod
    @log_exceptions()
    def get_or_create_social_user(email, first_name="", last_name=""):
        email = User.objects.normalize_email(email)
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
            },
        )
        return user, created

    @staticmethod
    def register_with_password(
        *,
        email,
        password,
        first_name="",
        last_name="",
        handle=None,
    ):
        email = User.objects.normalize_email(email)
        handle = handle.strip() if handle else None

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            CustomLogger.exception(
                "Password validation failed in register_with_password",
                extra={"email": email, "handle": handle},
            )
            raise ValueError(exc.messages)

        try:
            with transaction.atomic():
                return User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    handle=handle,
                )
        except IntegrityError:
            CustomLogger.exception(
                "User creation failed in register_with_password",
                extra={"email": email, "handle": handle},
            )
            raise ValueError("A user with this email or handle already exists.")

    @staticmethod
    @log_exceptions()
    def sign_in_with_password(*, username, password, request=None):
        username = username.strip()
        user = User.objects.filter(
            Q(email__iexact=username) | Q(handle__iexact=username)
        ).first()

        if not user:
            raise ValueError("Invalid username or password.")

        authenticated_user = authenticate(
            request=request,
            username=user.email,
            password=password,
        )

        if not authenticated_user:
            raise ValueError("Invalid username or password.")

        return authenticated_user

    @staticmethod
    @log_exceptions()
    def get_auth_tokens(user):
        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
