from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from oauth2_provider.generators import generate_client_id, generate_client_secret
from oauth2_provider.models import AccessToken, Application, RefreshToken

from users.models import User
from utils.custom_logger import CustomLogger


class DeveloperApplicationService:
    """Business logic for developers managing their OAuth applications."""

    @staticmethod
    def list_applications(user: User):
        """Returns all applications owned by the given developer."""
        return Application.objects.filter(user=user).order_by("-created")

    @staticmethod
    def get_application(user: User, client_id: str) -> Application:
        """Fetch a specific application owned by the user or raise ValueError."""
        app = Application.objects.filter(user=user, client_id=client_id).first()
        if not app:
            raise ValueError(f"Application '{client_id}' not found.")
        return app

    @classmethod
    def create_application(cls, user: User, data: dict) -> Application:
        """
        Creates an OAuth application for the developer.
        Generates client_id and (if confidential) client_secret.
        The raw client secret is attached transiently as `app.raw_client_secret`
        before being saved/hashed into the database.
        """
        name = data.get("name", "").strip()
        client_type = data.get("client_type", Application.CLIENT_CONFIDENTIAL)
        redirect_uris = data.get("redirect_uris", "").strip()
        allowed_origins = data.get("allowed_origins", "").strip()
        post_logout_redirect_uris = data.get("post_logout_redirect_uris", "").strip()
        algorithm = data.get("algorithm", "").strip()

        client_id = generate_client_id()
        if client_type == Application.CLIENT_CONFIDENTIAL:
            raw_secret = generate_client_secret()
        else:
            raw_secret = ""

        app = Application(
            user=user,
            name=name,
            client_id=client_id,
            client_secret=raw_secret,
            hash_client_secret=True,
            client_type=client_type,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=redirect_uris,
            allowed_origins=allowed_origins,
            post_logout_redirect_uris=post_logout_redirect_uris,
            algorithm=algorithm,
        )

        try:
            app.full_clean()
        except DjangoValidationError as exc:
            CustomLogger.warning(
                "Application validation failed during creation",
                extra={"user_id": str(user.id), "errors": exc.message_dict},
            )
            raise ValueError(exc.message_dict) from exc

        app.save()

        # Retain raw secret on instance for the single response back to developer
        app.raw_client_secret = raw_secret

        CustomLogger.info(
            "Developer OAuth application created",
            extra={
                "user_id": str(user.id),
                "client_id": client_id,
                "client_type": client_type,
            },
        )
        return app

    @classmethod
    def update_application(cls, user: User, client_id: str, data: dict) -> Application:
        """Updates name, redirect_uris, allowed_origins, or post_logout_redirect_uris."""
        app = cls.get_application(user, client_id)

        if "name" in data and data["name"] is not None:
            app.name = data["name"].strip()

        if "redirect_uris" in data and data["redirect_uris"] is not None:
            app.redirect_uris = data["redirect_uris"].strip()

        if "allowed_origins" in data and data["allowed_origins"] is not None:
            app.allowed_origins = data["allowed_origins"].strip()

        if "post_logout_redirect_uris" in data and data["post_logout_redirect_uris"] is not None:
            app.post_logout_redirect_uris = data["post_logout_redirect_uris"].strip()

        try:
            app.full_clean()
        except DjangoValidationError as exc:
            CustomLogger.warning(
                "Application validation failed during update",
                extra={"user_id": str(user.id), "client_id": client_id, "errors": exc.message_dict},
            )
            raise ValueError(exc.message_dict) from exc

        app.save()
        CustomLogger.info(
            "Developer OAuth application updated",
            extra={"user_id": str(user.id), "client_id": client_id},
        )
        return app

    @classmethod
    def delete_application(cls, user: User, client_id: str) -> None:
        """Deletes the application and purges all active tokens."""
        app = cls.get_application(user, client_id)

        with transaction.atomic():
            AccessToken.objects.filter(application=app).delete()
            RefreshToken.objects.filter(application=app).delete()
            app.delete()

        CustomLogger.info(
            "Developer OAuth application deleted",
            extra={"user_id": str(user.id), "client_id": client_id},
        )

    @classmethod
    def regenerate_client_secret(cls, user: User, client_id: str) -> str:
        """
        Regenerates client_secret for a confidential application.
        Returns the raw new client secret.
        """
        app = cls.get_application(user, client_id)

        if app.client_type != Application.CLIENT_CONFIDENTIAL:
            raise ValueError("Public applications do not use client secrets.")

        new_raw_secret = generate_client_secret()
        app.client_secret = new_raw_secret
        app.save()

        CustomLogger.info(
            "Developer OAuth application client secret rotated",
            extra={"user_id": str(user.id), "client_id": client_id},
        )
        return new_raw_secret

    @staticmethod
    def get_active_users_count(app: Application) -> int:
        """Returns the number of unique users with non-expired access tokens for this app."""
        now = timezone.now()
        return (
            AccessToken.objects.filter(application=app, expires__gt=now)
            .values("user")
            .distinct()
            .count()
        )

