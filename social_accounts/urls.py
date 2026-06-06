from django.urls import path
from .views import (
    YoutubeAuthViewSet,
    FacebookAuthConnectView,
    InstagramAuthConnectView,
    TiktokAuthConnectView,
    LinkedinAuthConnectView,
)

urlpatterns = [
    # YouTube uses a ViewSet with auth-url and connect actions
    path('youtube/auth-url/', YoutubeAuthViewSet.as_view({'get': 'auth_url'}), name='youtube-auth-url'),
    path('youtube/connect/', YoutubeAuthViewSet.as_view({'post': 'connect'}), name='youtube-auth-connect'),
    # Other platforms use simple APIViews
    path('facebook/connect/', FacebookAuthConnectView.as_view(), name='facebook-auth-connect'),
    path('instagram/connect/', InstagramAuthConnectView.as_view(), name='instagram-auth-connect'),
    path('tiktok/connect/', TiktokAuthConnectView.as_view(), name='tiktok-auth-connect'),
    path('linkedin/connect/', LinkedinAuthConnectView.as_view(), name='linkedin-auth-connect'),
]
