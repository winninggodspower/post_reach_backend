from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from content.enums import PostStatus
from content.models import ContentPost, ContentPostPlatform
from content.services.content_post_service import ContentPostService
from content.tasks import publish_scheduled_posts
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount


@pytest.fixture
def connected_accounts(brand):
    # Setup social account connections
    SocialAccount.objects.create(
        brand=brand,
        platform=PlatformChoices.FACEBOOK,
        account_name="FbPage",
        external_id="fb_123",
        access_token="token",
        token_expires_at=timezone.now() + timedelta(days=1),
    )
    SocialAccount.objects.create(
        brand=brand,
        platform=PlatformChoices.INSTAGRAM,
        account_name="IgPage",
        external_id="ig_123",
        access_token="token",
        token_expires_at=timezone.now() + timedelta(days=1),
    )


@pytest.mark.django_db
class TestPostScheduling:
    def test_create_scheduled_post(self, user, brand, connected_accounts, mocker):
        # Mock Celery delay method to make sure it is not called
        mock_delay = mocker.patch("content.tasks.wait_for_media_and_publish_platform_entry.delay")

        future_time = timezone.now() + timedelta(hours=2)
        post = ContentPostService.create_content_post(
            user=user,
            media_files=[],
            caption="Scheduled Post",
            platforms=["facebook", "instagram"],
            content_type="text",
            scheduled_at=future_time,
        )

        assert post.scheduled_at == future_time
        assert post.caption == "Scheduled Post"

        # Check platform entries status
        platforms = post.platform_entries.all()
        assert len(platforms) == 2
        for entry in platforms:
            assert entry.status == PostStatus.SCHEDULED

        # Ensure task was NOT dispatched
        mock_delay.assert_not_called()

    def test_celery_periodic_task_triggers_due_posts(
        self, user, brand, connected_accounts, mocker
    ):
        mock_delay = mocker.patch("content.tasks.wait_for_media_and_publish_platform_entry.delay")

        past_time = timezone.now() - timedelta(minutes=5)
        future_time = timezone.now() + timedelta(hours=1)

        # 1. Post due to be published
        due_post = ContentPostService.create_content_post(
            user=user,
            media_files=[],
            caption="Due Post",
            platforms=["facebook"],
            content_type="text",
            scheduled_at=past_time,
        )

        # 2. Post not yet due
        future_post = ContentPostService.create_content_post(
            user=user,
            media_files=[],
            caption="Future Post",
            platforms=["facebook"],
            content_type="text",
            scheduled_at=future_time,
        )

        # Run periodic task
        publish_scheduled_posts()

        # Check due post status updated to PENDING and dispatched
        due_entry = ContentPostPlatform.objects.get(content_post=due_post)
        assert due_entry.status == PostStatus.PENDING
        mock_delay.assert_called_once_with(str(due_entry.id), content_type="text")

        # Check future post remains SCHEDULED
        future_entry = ContentPostPlatform.objects.get(content_post=future_post)
        assert future_entry.status == PostStatus.SCHEDULED

    def test_calendar_endpoint_filtering(
        self, authenticated_client, user, brand, connected_accounts
    ):
        now = timezone.now()

        # Post 1: Scheduled today
        post_today = ContentPostService.create_content_post(
            user=user,
            media_files=[],
            caption="Today",
            platforms=["facebook"],
            content_type="text",
            scheduled_at=now,
        )

        # Post 2: Scheduled next week
        post_next_week = ContentPostService.create_content_post(
            user=user,
            media_files=[],
            caption="Next Week",
            platforms=["facebook"],
            content_type="text",
            scheduled_at=now + timedelta(days=7),
        )

        url = reverse("content-post-calendar")

        # Test range covering only today
        start_date = now.strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")

        response = authenticated_client.get(
            url, {"start_date": start_date, "end_date": end_date}
        )
        assert response.status_code == 200
        data = response.data
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == str(post_today.id)

        # Test range covering both
        end_date_extended = (now + timedelta(days=10)).strftime("%Y-%m-%d")
        response = authenticated_client.get(
            url, {"start_date": start_date, "end_date": end_date_extended}
        )
        assert response.status_code == 200
        assert len(response.data["data"]) == 2
