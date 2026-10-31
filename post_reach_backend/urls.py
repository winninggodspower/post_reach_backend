from django.contrib import admin
from django.urls import include, path, re_path
from oauth2_provider import urls as oauth2_urls

from mcp_integration.views import PostGleeMCPView

from .swagger import developer_schema_view, schema_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/api-auth/", include("rest_framework.urls")),
    path("api/auth/", include("users.urls")),
    path("api/oauth/", include("mcp_integration.urls")),
    path("api/social_accounts/", include("social_accounts.urls")),
    path("api/content/", include("content.urls")),
    path("api/admin/analytics/", include("analytics.urls")),
    path("api/subscriptions/", include("subscriptions.urls")),
    path("api/developers/", include("developers.urls")),
    # Public Developer v1 API documentation (OpenAPI schema & Swagger/ReDoc UIs)
    re_path(
        r"^api/v1/swagger\.(?P<format>json|yaml)$",
        developer_schema_view.without_ui(cache_timeout=0),
        name="developer-schema-json",
    ),
    re_path(
        r"^api/v1/openapi\.(?P<format>json|yaml)$",
        developer_schema_view.without_ui(cache_timeout=0),
        name="developer-openapi-json",
    ),
    path(
        "api/v1/docs/",
        developer_schema_view.with_ui("swagger", cache_timeout=0),
        name="developer-schema-swagger-ui",
    ),
    path(
        "api/v1/redoc/",
        developer_schema_view.with_ui("redoc", cache_timeout=0),
        name="developer-schema-redoc",
    ),
    # Public Developer v1 REST API
    path("api/v1/", include("developers.v1.urls")),
    # OAuth 2.1 discovery metadata at root (/.well-known/*) and OAuth endpoints at /oauth/*
    *oauth2_urls.metadata_urlpatterns,
    path("oauth/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    # Remote MCP server endpoint (Streamable HTTP)
    path("mcp", PostGleeMCPView.as_view(), name="mcp-server"),
    path("mcp/", PostGleeMCPView.as_view(), name="mcp-server-slash"),
    # Internal Swagger & ReDoc (strictly restricted to staff/admin users)
    re_path(
        r"^swagger\.(?P<format>json|yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
]
