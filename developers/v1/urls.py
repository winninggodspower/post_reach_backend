from django.urls import path

from developers.v1.views import (
    AccountListView,
    BrandListView,
    PostCalendarView,
    PostDetailView,
    PostListCreateView,
)

urlpatterns = [
    # Brands & Connected Accounts (scope: accounts:read)
    path("brands/", BrandListView.as_view(), name="v1-brand-list"),
    path("accounts/", AccountListView.as_view(), name="v1-account-list"),
    # Posts & Calendar (scopes: posts:read, posts:write)
    path("posts/", PostListCreateView.as_view(), name="v1-post-list-create"),
    path("posts/calendar/", PostCalendarView.as_view(), name="v1-post-calendar"),
    path("posts/<uuid:post_id>/", PostDetailView.as_view(), name="v1-post-detail"),
]
