from django.urls import path
from .views import (
    YoutubeAuthViewSet,
    FacebookAuthViewSet,
    InstagramAuthViewSet,
    TiktokAuthViewSet,
    LinkedinAuthViewSet,
)

urlpatterns = [
    # YouTube uses a ViewSet with auth-url and connect actions
    path('youtube/auth-url/', YoutubeAuthViewSet.as_view({'get': 'auth_url'}), name='youtube-auth-url'),
    path('youtube/connect/', YoutubeAuthViewSet.as_view({'post': 'connect'}), name='youtube-auth-connect'),
    # Facebook uses a ViewSet with auth-url and connect actions (same pattern as YouTube)
    path('facebook/auth-url/', FacebookAuthViewSet.as_view({'get': 'auth_url'}), name='facebook-auth-url'),
    path('facebook/connect/', FacebookAuthViewSet.as_view({'post': 'connect'}), name='facebook-auth-connect'),
    # Instagram uses a ViewSet with auth-url and connect actions (same pattern as Facebook/YouTube)
    path('instagram/auth-url/', InstagramAuthViewSet.as_view({'get': 'auth_url'}), name='instagram-auth-url'),
    path('instagram/connect/', InstagramAuthViewSet.as_view({'post': 'connect'}), name='instagram-auth-connect'),
    # TikTok uses a ViewSet with auth-url and connect actions (same pattern as Facebook/YouTube/Instagram)
    path('tiktok/auth-url/', TiktokAuthViewSet.as_view({'get': 'auth_url'}), name='tiktok-auth-url'),
    path('tiktok/connect/', TiktokAuthViewSet.as_view({'post': 'connect'}), name='tiktok-auth-connect'),
    # LinkedIn uses a ViewSet with auth-url and connect actions (same pattern as the others)
    path('linkedin/auth-url/', LinkedinAuthViewSet.as_view({'get': 'auth_url'}), name='linkedin-auth-url'),
    path('linkedin/connect/', LinkedinAuthViewSet.as_view({'post': 'connect'}), name='linkedin-auth-connect'),
]
