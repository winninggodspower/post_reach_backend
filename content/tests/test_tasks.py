from unittest.mock import MagicMock

import pytest
from celery.exceptions import Retry
from django.utils import timezone

from content.enums import PostStatus
from content.models import ContentPost, ContentPostPlatform, PendingUpload
from content.tasks import (
    check_instagram_container_status,
    cleanup_abandoned_pending_uploads,
    publish_platform_entry,
)
from integrations.providers.instagram_service import InstagramService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount

pytestmark = pytest.mark.django_db


class TestPublishPlatformEntryTask:
    """Tests for the publish_platform_entry Celery task."""

    def test_publish_platform_entry_queues_status_check(self, mocker, user, brand):
        """Should queue check_instagram_container_status if status is UPLOADING for Instagram."""
        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.INSTAGRAM,
            account_name="acct_ig",
            external_id="17841400797787220",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )

        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Test", content_type="video"
        )
        entry = ContentPostPlatform.objects.create(
            content_post=cp, platform=PlatformChoices.INSTAGRAM
        )

        # Mock posting service to return UPLOADING status (as if container created)
        mocker.patch(
            "content.services.posting_service.PostingService.publish_platform_entry",
            return_value=mocker.Mock(
                id=entry.id,
                status=PostStatus.PROCESSING,
                platform=PlatformChoices.INSTAGRAM,
                content_post=cp,
                platform_post_id="container_123",
            ),
        )

        mock_delay = mocker.patch(
            "content.tasks.check_instagram_container_status.delay"
        )

        result = publish_platform_entry(entry.id, content_type="video")

        assert result["status"] == PostStatus.PROCESSING
        mock_delay.assert_called_once_with(str(entry.id))


class TestCheckInstagramContainerStatusTask:
    """Tests for the check_instagram_container_status Celery task."""

    def test_check_status_in_progress_retries(self, mocker, user, brand):
        """Should raise Retry when status is IN_PROGRESS."""
        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.INSTAGRAM,
            account_name="acct_ig",
            external_id="17841400797787220",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )

        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Test", content_type="video"
        )
        entry = ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.UPLOADING,
            platform_post_id="container_123",
        )

        mocker.patch.object(
            InstagramService,
            "check_container_status",
            return_value="IN_PROGRESS",
        )

        # Mock task.retry to raise a Retry exception (simulating Celery behavior)
        mock_retry = mocker.patch(
            "content.tasks.check_instagram_container_status.retry",
            side_effect=Retry(),
        )

        with pytest.raises(Retry):
            check_instagram_container_status(entry.id)

        mock_retry.assert_called_once()

    def test_check_status_finished_publishes_reels(self, mocker, user, brand):
        """Should publish Reels container and update status to POSTED when status is FINISHED."""
        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.INSTAGRAM,
            account_name="acct_ig",
            external_id="17841400797787220",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )

        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Test", content_type="video"
        )
        entry = ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.UPLOADING,
            platform_post_id="container_123",
        )

        mocker.patch.object(
            InstagramService,
            "check_container_status",
            return_value="FINISHED",
        )

        mock_pub = mocker.patch.object(
            InstagramService,
            "publish_container",
            return_value={"platform_post_id": "media_999"},
        )

        mock_cleanup = mocker.patch(
            "content.services.posting_service.PostingService.cleanup_r2_media"
        )

        mock_permalink = mocker.patch.object(
            InstagramService,
            "get_permalink",
            return_value="https://instagram.com/p/123/",
        )

        result = check_instagram_container_status(entry.id)

        assert result["status"] == "posted"
        assert result["platform_post_id"] == "media_999"

        # Verify entry updated in DB
        entry.refresh_from_db()
        assert entry.status == PostStatus.POSTED
        assert entry.platform_post_id == "media_999"

        mock_pub.assert_called_once_with(
            access_token="token",
            instagram_account_id="17841400797787220",
            container_id="container_123",
        )
        mock_cleanup.assert_called_once_with(cp)


class TestCleanupAbandonedPendingUploadsTask:
    def test_cleanup_abandoned_uploads(self, mocker, user):
        """Should delete unclaimed uploads older than 24h, keep claimed and recent uploads."""
        mock_delete_r2 = mocker.patch("utils.r2_storage.R2StorageService.delete_file")

        # 1. Unclaimed and older than 24 hours -> Should be deleted
        old_time = timezone.now() - timezone.timedelta(hours=25)
        abandoned = PendingUpload.objects.create(
            user=user,
            r2_key="videos/abandoned.mp4",
            content_type="video",
            is_claimed=False,
        )
        PendingUpload.objects.filter(id=abandoned.id).update(created_at=old_time)

        # 2. Claimed and older than 24 hours (e.g. scheduled post) -> Should NOT be deleted
        claimed_old = PendingUpload.objects.create(
            user=user,
            r2_key="videos/scheduled.mp4",
            content_type="video",
            is_claimed=True,
        )
        PendingUpload.objects.filter(id=claimed_old.id).update(created_at=old_time)

        # 3. Unclaimed but recent (<24h) -> Should NOT be deleted
        recent = PendingUpload.objects.create(
            user=user,
            r2_key="videos/recent.mp4",
            content_type="video",
            is_claimed=False,
        )

        cleanup_abandoned_pending_uploads()

        # R2 delete called only for abandoned
        mock_delete_r2.assert_called_once_with("videos/abandoned.mp4")

        # DB checks
        assert not PendingUpload.objects.filter(id=abandoned.id).exists()
        assert PendingUpload.objects.filter(id=claimed_old.id).exists()
        assert PendingUpload.objects.filter(id=recent.id).exists()
