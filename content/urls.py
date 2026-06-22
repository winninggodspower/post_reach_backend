from django.urls import path, re_path

from .views import ContentPostViewSet

urlpatterns = [
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
        "posts/<uuid:pk>/",
        ContentPostViewSet.as_view({"get": "retrieve"}),
        name="content-post-detail",
    ),
]
