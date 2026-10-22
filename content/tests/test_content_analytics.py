from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from content.enums import PostStatus
from content.models import ContentPost, ContentPostPlatform, PostPlatformMetric
from content.services.content_analytics_service import ContentAnalyticsService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount

pytestmark = pytest.mark.django_db


@pytest.fixture
def post(user, brand):
    return ContentPost.objects.create(
        user=user,
        brand=brand,
        caption="Exciting update for everyone!",
        content_type="video",
    )


@pytest.fixture
def youtube_entry(post):
    return ContentPostPlatform.objects.create(
        content_post=post,
        platform=PlatformChoices.YOUTUBE,
        status=PostStatus.POSTED,
        platform_post_id="yt_video_123",
        post_url="https://youtube.com/watch?v=yt_video_123",
    )


@pytest.fixture
def instagram_entry(post):
    return ContentPostPlatform.objects.create(
        content_post=post,
        platform=PlatformChoices.INSTAGRAM,
        status=PostStatus.POSTED,
        platform_post_id="ig_media_456",
        post_url="https://instagram.com/p/ig_media_456",
    )


@pytest.fixture
def connected_youtube_account(brand):
    account = SocialAccount(
        brand=brand,
        platform=PlatformChoices.YOUTUBE,
        account_name="Acme Channel",
        external_id="yt_channel_1",
        token_expires_at=timezone.now() + timedelta(days=30),
    )
    account.access_token = "valid_yt_token"
    account.save()
    return account


@pytest.fixture
def connected_instagram_account(brand):
    account = SocialAccount(
        brand=brand,
        platform=PlatformChoices.INSTAGRAM,
        account_name="@acme_brand",
        external_id="ig_user_1",
        token_expires_at=timezone.now() + timedelta(days=30),
    )
    account.access_token = "valid_ig_token"
    account.save()
    return account


class TestContentAnalyticsService:
    @patch("integrations.providers.youtube_service.YoutubeService.get_post_metrics")
    def test_sync_platform_post_metric_from_provider(
        self, mock_metrics, youtube_entry, connected_youtube_account
    ):
        mock_metrics.return_value = {
            "views": 1500,
            "likes": 120,
            "comments": 30,
            "shares": 10,
            "raw": {"mocked": True},
        }

        metric = ContentAnalyticsService.sync_platform_post_metric(youtube_entry)

        assert metric.views == 1500
        assert metric.likes == 120
        assert metric.comments == 30
        assert metric.shares == 10
        # (120 + 30 + 10) / 1500 * 100 = 10.67%
        assert metric.engagement_rate == 10.67
        mock_metrics.assert_called_once()

    @patch("integrations.providers.youtube_service.YoutubeService.get_post_metrics")
    def test_sync_cached_when_under_one_hour(
        self, mock_metrics, youtube_entry, connected_youtube_account
    ):
        mock_metrics.return_value = {
            "views": 500,
            "likes": 20,
            "comments": 5,
            "shares": 0,
        }

        # First sync
        metric1 = ContentAnalyticsService.sync_platform_post_metric(youtube_entry)
        assert mock_metrics.call_count == 1

        # Second sync within 1 hour without force
        metric2 = ContentAnalyticsService.sync_platform_post_metric(
            youtube_entry, force=False
        )
        assert mock_metrics.call_count == 1  # Should not be called again!
        assert metric2.id == metric1.id

    @patch("integrations.providers.youtube_service.YoutubeService.get_post_metrics")
    def test_sync_force_refresh_bypasses_cache(
        self, mock_metrics, youtube_entry, connected_youtube_account
    ):
        mock_metrics.side_effect = [
            {"views": 500, "likes": 20, "comments": 5, "shares": 0},
            {"views": 900, "likes": 50, "comments": 15, "shares": 2},
        ]

        # First sync
        ContentAnalyticsService.sync_platform_post_metric(youtube_entry)
        assert mock_metrics.call_count == 1

        # Force refresh
        metric2 = ContentAnalyticsService.sync_platform_post_metric(
            youtube_entry, force=True
        )
        assert mock_metrics.call_count == 2
        assert metric2.views == 900
        assert metric2.likes == 50

    @patch("integrations.providers.instagram_service.InstagramService.get_post_metrics")
    @patch("integrations.providers.youtube_service.YoutubeService.get_post_metrics")
    def test_get_or_sync_post_analytics_aggregates(
        self,
        mock_yt,
        mock_ig,
        post,
        youtube_entry,
        instagram_entry,
        connected_youtube_account,
        connected_instagram_account,
    ):
        mock_yt.return_value = {
            "views": 1000,
            "likes": 100,
            "comments": 20,
            "shares": 10,
        }
        mock_ig.return_value = {
            "views": 2000,
            "reach": 1800,
            "likes": 250,
            "comments": 30,
            "shares": 20,
            "saves": 15,
        }

        analytics = ContentAnalyticsService.get_or_sync_post_analytics(post)

        assert analytics["total_views"] == 3000
        assert analytics["total_likes"] == 350
        assert analytics["total_comments"] == 50
        assert analytics["total_shares"] == 30
        assert analytics["total_saves"] == 15
        assert len(analytics["platforms"]) == 2

    def test_get_brand_analytics(self, brand, post, youtube_entry):
        # Create metric directly
        PostPlatformMetric.objects.create(
            content_post_platform=youtube_entry,
            views=5000,
            likes=400,
            comments=80,
            shares=50,
            engagement_rate=10.6,
        )

        analytics = ContentAnalyticsService.get_brand_analytics(brand, days=30)

        assert analytics["brand_id"] == brand.id
        assert analytics["total_views"] == 5000
        assert analytics["total_likes"] == 400
        assert analytics["total_comments"] == 80
        assert len(analytics["top_posts"]) == 1
        assert analytics["top_posts"][0]["views"] == 5000


class TestContentAnalyticsAPI:
    @patch("integrations.providers.youtube_service.YoutubeService.get_post_metrics")
    def test_get_post_analytics_endpoint(
        self,
        mock_yt,
        authenticated_client,
        post,
        youtube_entry,
        connected_youtube_account,
    ):
        mock_yt.return_value = {
            "views": 1200,
            "likes": 90,
            "comments": 15,
            "shares": 5,
        }

        url = reverse("content-post-analytics", kwargs={"post_id": post.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["post_id"] == str(post.id)
        assert data["total_views"] == 1200
        assert data["total_likes"] == 90
        assert len(data["platforms"]) == 1

    def test_get_post_analytics_forbidden_for_other_user(
        self, api_client, post, youtube_entry, django_user_model
    ):
        other_user = django_user_model.objects.create_user(
            email="intruder@example.com", password="Password123!"
        )
        api_client.force_authenticate(user=other_user)

        url = reverse("content-post-analytics", kwargs={"post_id": post.id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_brand_analytics_endpoint(
        self, authenticated_client, brand, post, youtube_entry
    ):
        PostPlatformMetric.objects.create(
            content_post_platform=youtube_entry,
            views=3500,
            likes=200,
            comments=45,
            shares=25,
            engagement_rate=7.71,
        )

        url = reverse("brand-content-analytics", kwargs={"brand_id": brand.id})
        response = authenticated_client.get(f"{url}?days=30")

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["brand_id"] == str(brand.id)
        assert data["total_views"] == 3500
        assert data["total_likes"] == 200
        assert len(data["top_posts"]) == 1

    def test_get_post_analytics_with_pending_entry_null_last_synced_at(
        self, authenticated_client, post
    ):
        # Create an entry that is still PENDING without platform_post_id or sync history
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.TIKTOK,
            status=PostStatus.PENDING,
            platform_post_id="",
            post_url="",
        )

        url = reverse("content-post-analytics", kwargs={"post_id": post.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert len(data["platforms"]) == 1
        platform_info = data["platforms"][0]
        assert platform_info["status"] == PostStatus.PENDING
        assert platform_info["last_synced_at"] is None
        assert platform_info["views"] == 0
