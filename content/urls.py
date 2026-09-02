from django.urls import path, re_path

from .views import ContentPostViewSet

urlpatterns = [
    path(
        "posts/presigned-url/",
        ContentPostViewSet.as_view({"post": "get_presigned_url"}),
        name="content-post-presigned-url",
    ),
    path(
        "posts/video/",
        ContentPostViewSet.as_view({"post": "create_video"}),
        name="content-post-video",
    ),
    path(
        "posts/photo/",
        ContentPostViewSet.as_view({"post": "create_photo"}),
        name="content-post-photo",
    ),
    path(
        "posts/text/",
        ContentPostViewSet.as_view({"post": "create_text"}),
        name="content-post-text",
    ),
    path(
        "posts/calendar/",
        ContentPostViewSet.as_view({"get": "get_calendar_posts"}),
        name="content-post-calendar",
    ),
    path(
        "posts/<uuid:pk>/",
        ContentPostViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="content-post-detail",
    ),
]
