from django.conf import settings
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.views import get_schema_view
from rest_framework import permissions


class InternalSwaggerPermission(permissions.BasePermission):
    """
    Allows full access during local development (DEBUG=True).
    Strictly restricts to staff and admin users in production (DEBUG=False).
    """

    def has_permission(self, request, view):
        if settings.DEBUG:
            return True
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff
        )


class BearerSchemaGenerator(OpenAPISchemaGenerator):
    """Adds Bearer JWT security scheme and global security requirement."""

    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.security_definitions = {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "JWT token obtained from /api/auth/login/. Use as: Bearer <token>",
            }
        }
        schema.security = [{"Bearer": []}]
        return schema


class DeveloperV1SchemaGenerator(OpenAPISchemaGenerator):
    """OpenAPI schema generator strictly isolated for PostGlee Developer v1 public APIs."""

    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.security_definitions = {
            "OAuth2": {
                "type": "oauth2",
                "flow": "accessCode",
                "authorizationUrl": "/oauth/authorize/",
                "tokenUrl": "/oauth/token/",
                "scopes": {
                    "accounts:read": "Read accessible brands and connected social media accounts.",
                    "posts:read": "Read scheduled, draft, and published social posts and calendar.",
                    "posts:write": "Create, edit, schedule, and publish social posts.",
                },
            },
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "OAuth 2.1 access token. Pass in Authorization header as: Bearer <access_token>",
            },
        }
        schema.security = [
            {"OAuth2": ["accounts:read", "posts:read", "posts:write"]},
            {"Bearer": []},
        ]
        return schema


# Internal API schema view: open in local dev (DEBUG=True), restricted to staff/admin in production
schema_view = get_schema_view(
    openapi.Info(
        title="PostGlee Internal API",
        default_version="v1",
        description="Internal backend API for PostGlee web application. Restricted to staff and admin users in production.",
        terms_of_service="https://postglee.com/terms/",
        contact=openapi.Contact(email="support@postglee.com"),
    ),
    public=True,
    permission_classes=(InternalSwaggerPermission,),
    generator_class=BearerSchemaGenerator,
)

# Developer v1 API schema view: public endpoints isolated for external developers, tools, and AI connectors
developer_v1_patterns = [
    path("api/v1/", include("developers.v1.urls")),
]

developer_schema_view = get_schema_view(
    openapi.Info(
        title="PostGlee Developer API",
        default_version="v1",
        description=(
            "Official public REST API for PostGlee developers, third-party integrations, and AI connectors.\n\n"
            "### Authentication\n"
            "Authenticate all requests using an OAuth 2.1 access token obtained via PostGlee OAuth:\n"
            "`Authorization: Bearer <access_token>`\n\n"
            "### Available Scopes\n"
            "- `accounts:read`: Access brands and connected social media profiles.\n"
            "- `posts:read`: Access scheduled and published posts and calendar views.\n"
            "- `posts:write`: Create, update, schedule, and publish social posts."
        ),
        terms_of_service="https://postglee.com/terms/",
        contact=openapi.Contact(email="support@postglee.com"),
    ),
    patterns=developer_v1_patterns,
    public=True,
    permission_classes=(permissions.AllowAny,),
    generator_class=DeveloperV1SchemaGenerator,
)
