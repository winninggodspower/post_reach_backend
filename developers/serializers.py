from oauth2_provider.models import Application
from rest_framework import serializers

from developers.services import DeveloperApplicationService


class ApplicationSerializer(serializers.ModelSerializer):
    """Serializer representing an OAuth application in the Developer Dashboard."""

    redirect_uris_list = serializers.SerializerMethodField()
    allowed_origins_list = serializers.SerializerMethodField()
    post_logout_redirect_uris_list = serializers.SerializerMethodField()
    active_users_count = serializers.SerializerMethodField()
    client_secret = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "name",
            "client_id",
            "client_secret",
            "client_type",
            "authorization_grant_type",
            "redirect_uris",
            "redirect_uris_list",
            "allowed_origins",
            "allowed_origins_list",
            "post_logout_redirect_uris",
            "post_logout_redirect_uris_list",
            "algorithm",
            "created",
            "updated",
            "active_users_count",
        ]
        read_only_fields = fields

    def get_redirect_uris_list(self, obj: Application) -> list[str]:
        return obj.redirect_uris.split() if obj.redirect_uris else []

    def get_allowed_origins_list(self, obj: Application) -> list[str]:
        return obj.allowed_origins.split() if obj.allowed_origins else []

    def get_post_logout_redirect_uris_list(self, obj: Application) -> list[str]:
        return (
            obj.post_logout_redirect_uris.split()
            if obj.post_logout_redirect_uris
            else []
        )

    def get_active_users_count(self, obj: Application) -> int:
        return DeveloperApplicationService.get_active_users_count(obj)

    def get_client_secret(self, obj: Application) -> str | None:
        # Only expose raw_client_secret if set transiently during creation
        if hasattr(obj, "raw_client_secret"):
            return obj.raw_client_secret
        return None


class ApplicationCreateSerializer(serializers.Serializer):
    """Input serializer for registering a new Developer OAuth application."""

    name = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Name of your application visible to users when authorizing access.",
    )
    client_type = serializers.ChoiceField(
        choices=[Application.CLIENT_CONFIDENTIAL, Application.CLIENT_PUBLIC],
        default=Application.CLIENT_CONFIDENTIAL,
        help_text=(
            "'confidential' for web servers with backend storage for client secret; "
            "'public' for SPAs or mobile clients using PKCE without a secret."
        ),
    )
    redirect_uris = serializers.CharField(
        required=True,
        help_text="Allowed callback URLs separated by spaces or newlines (or pass an array).",
    )
    allowed_origins = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Allowed CORS origins for browser-based authorization requests.",
    )
    post_logout_redirect_uris = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Allowed redirect URIs after user logs out.",
    )
    algorithm = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Token signing algorithm (leave blank for standard defaults).",
    )

    def to_internal_value(self, data):
        # Support array input for redirect_uris, allowed_origins, and post_logout_redirect_uris
        data_copy = data.copy() if hasattr(data, "copy") else dict(data)
        for field in ["redirect_uris", "allowed_origins", "post_logout_redirect_uris"]:
            val = data_copy.get(field)
            if isinstance(val, list):
                data_copy[field] = " ".join(
                    str(item).strip() for item in val if str(item).strip()
                )
        return super().to_internal_value(data_copy)

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Application name cannot be empty.")
        return cleaned

    def validate_redirect_uris(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError(
                "At least one valid redirect URI is required."
            )
        return cleaned


class ApplicationUpdateSerializer(serializers.Serializer):
    """Input serializer for updating an existing Developer OAuth application."""

    name = serializers.CharField(
        max_length=255,
        required=False,
        help_text="Updated name of your application.",
    )
    redirect_uris = serializers.CharField(
        required=False,
        help_text="Allowed callback URLs separated by spaces or newlines.",
    )
    allowed_origins = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Allowed CORS origins for browser-based authorization requests.",
    )
    post_logout_redirect_uris = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Allowed redirect URIs after user logs out.",
    )

    def to_internal_value(self, data):
        data_copy = data.copy() if hasattr(data, "copy") else dict(data)
        for field in ["redirect_uris", "allowed_origins", "post_logout_redirect_uris"]:
            if field in data_copy:
                val = data_copy[field]
                if isinstance(val, list):
                    data_copy[field] = " ".join(
                        str(item).strip() for item in val if str(item).strip()
                    )
        return super().to_internal_value(data_copy)

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Application name cannot be empty.")
        return cleaned


class RegenerateSecretResponseSerializer(serializers.Serializer):
    client_id = serializers.CharField()
    client_secret = serializers.CharField()
    message = serializers.CharField()
