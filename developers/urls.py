from django.urls import path

from developers.views import (
    DeveloperApplicationDetailView,
    DeveloperApplicationListCreateView,
    DeveloperApplicationSecretRegenerateView,
    DeveloperScopesView,
)

urlpatterns = [
    path(
        "applications/",
        DeveloperApplicationListCreateView.as_view(),
        name="developer-application-list-create",
    ),
    path(
        "applications/<str:client_id>/",
        DeveloperApplicationDetailView.as_view(),
        name="developer-application-detail",
    ),
    path(
        "applications/<str:client_id>/regenerate-secret/",
        DeveloperApplicationSecretRegenerateView.as_view(),
        name="developer-application-regenerate-secret",
    ),
    path(
        "scopes/",
        DeveloperScopesView.as_view(),
        name="developer-scopes",
    ),
]
