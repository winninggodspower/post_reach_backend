from django.urls import path

from mcp_integration.views import OAuthConnectionDetailView, OAuthConnectionListView

urlpatterns = [
    path(
        "connections/",
        OAuthConnectionListView.as_view(),
        name="oauth-connection-list",
    ),
    path(
        "connections/<str:client_id>/",
        OAuthConnectionDetailView.as_view(),
        name="oauth-connection-detail",
    ),
]
