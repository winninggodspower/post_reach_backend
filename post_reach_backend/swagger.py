from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.views import get_schema_view
from rest_framework import permissions


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


schema_view = get_schema_view(
    openapi.Info(
        title="Re API",
        default_version="v1",
        description="Post Reach Backend API",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@snippets.local"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    generator_class=BearerSchemaGenerator,
)
