from unittest.mock import MagicMock, patch

import pytest
from django.core import mail

from content.enums import PostStatus
from content.models import ContentPost, ContentPostPlatform
from content.services.posting_service import PostingService
from content.tasks import send_post_status_notification_task
from social_accounts.enums import PlatformChoices
from utils.notification_service import NotificationService

pytestmark = pytest.mark.django_db


class TestNotificationService:
    def test_send_post_status_notification_all_succeeded(self, user, brand):
        """Should send a live notification email with post links when all platforms succeed."""
        cp = ContentPost.objects.create(
            user=user,
            brand=brand,
            caption="Check out my new video!",
            content_type="video",
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.POSTED,
            post_url="https://instagram.com/p/abc123",
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.TIKTOK,
            status=PostStatus.POSTED,
            post_url="https://tiktok.com/@user/video/999",
        )

        sent = NotificationService.send_post_status_notification(content_post_id=cp.id)

        assert sent is True
        assert len(mail.outbox) == 1
        email = mail.outbox[0]

        assert email.to == [user.email]
        assert "Your post is live on" in email.subject
        assert "Instagram" in email.subject
        assert "TikTok" in email.subject
        assert (
            "https://instagram.com/p/abc123" in email.body
            or "https://instagram.com/p/abc123" in email.alternatives[0][0]
        )
        assert "Check out my new video!" in email.alternatives[0][0]

        # Verify idempotency field updated
        cp.refresh_from_db()
        assert cp.email_notified_at is not None

    def test_send_post_status_notification_all_failed(self, user, brand):
        """Should send a failure notification email stating the exact failure reason."""
        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Failing post content", content_type="photo"
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.FAILED,
            error_message="Invalid OAuth access token or permissions revoked.",
        )

        sent = NotificationService.send_post_status_notification(content_post_id=cp.id)

        assert sent is True
        assert len(mail.outbox) == 1
        email = mail.outbox[0]

        assert email.to == [user.email]
        assert "Failed to publish your post on Facebook" in email.subject
        # Crucial requirement: Failure reason MUST be stated in the email
        html_content = email.alternatives[0][0]
        assert "Invalid OAuth access token or permissions revoked." in html_content
        assert "Facebook" in html_content

        cp.refresh_from_db()
        assert cp.email_notified_at is not None

    def test_send_post_status_notification_mixed_results(self, user, brand):
        """Should send a consolidated email showing both live links and failure reasons."""
        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Multi-platform post", content_type="video"
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.POSTED,
            post_url="https://youtube.com/watch?v=xyz",
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.LINKEDIN,
            status=PostStatus.FAILED,
            error_message="LinkedIn API rate limit exceeded.",
        )

        sent = NotificationService.send_post_status_notification(content_post_id=cp.id)

        assert sent is True
        assert len(mail.outbox) == 1
        email = mail.outbox[0]

        html_content = email.alternatives[0][0]
        assert "YouTube" in html_content
        assert "https://youtube.com/watch?v=xyz" in html_content
        assert "LinkedIn" in html_content
        assert "LinkedIn API rate limit exceeded." in html_content

    def test_send_post_status_notification_idempotent(self, user, brand):
        """Should not send another email if email_notified_at is already set."""
        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Idempotency test"
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.POSTED,
            post_url="https://instagram.com/p/test",
        )

        # First send
        assert (
            NotificationService.send_post_status_notification(content_post_id=cp.id)
            is True
        )
        assert len(mail.outbox) == 1

        # Second send attempt
        assert (
            NotificationService.send_post_status_notification(content_post_id=cp.id)
            is False
        )
        assert len(mail.outbox) == 1  # Still 1, no duplicate sent

    def test_does_not_send_when_platform_entries_still_pending(self, user, brand):
        """Should postpone notification if any platform entry is still pending or processing."""
        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Multi-step test"
        )
        # Platform 1 is posted
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.POSTED,
            post_url="https://facebook.com/post/1",
        )
        # Platform 2 is still processing
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.PROCESSING,
        )

        sent = NotificationService.send_post_status_notification(content_post_id=cp.id)
        assert sent is False
        assert len(mail.outbox) == 0

        cp.refresh_from_db()
        assert cp.email_notified_at is None

    def test_on_platform_entry_completed_dispatches_task_when_all_done(
        self, user, brand, mocker
    ):
        """PostingService.on_platform_entry_completed triggers task when all entries are done."""
        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Entry completed test"
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.POSTED,
        )

        mock_delay = mocker.patch(
            "content.tasks.send_post_status_notification_task.delay"
        )
        mocker.patch.object(PostingService, "cleanup_r2_media")

        PostingService.on_platform_entry_completed(cp)

        mock_delay.assert_called_once_with(str(cp.id))

    def test_on_platform_entry_completed_waits_if_entries_pending(
        self, user, brand, mocker
    ):
        """PostingService.on_platform_entry_completed does not trigger task if entries are pending."""
        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Entry pending test"
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.POSTED,
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.UPLOADING,
        )

        mock_delay = mocker.patch(
            "content.tasks.send_post_status_notification_task.delay"
        )
        mocker.patch.object(PostingService, "cleanup_r2_media")

        PostingService.on_platform_entry_completed(cp)

        mock_delay.assert_not_called()

    def test_send_post_status_notification_task(self, user, brand, mocker):
        """Celery task executes send_post_status_notification properly."""
        mock_send = mocker.patch(
            "utils.notification_service.NotificationService.send_post_status_notification",
            return_value=True,
        )

        res = send_post_status_notification_task("some-post-id")
        assert res == {"status": "success", "sent": True}
        mock_send.assert_called_once_with(content_post_id="some-post-id")


class TestFailedPostMediaRetention:
    def test_cleanup_r2_media_retains_files_on_failure(self, user, brand, mocker):
        """Should NOT delete R2 files immediately if a platform failed (retained for retry)."""
        from content.models import ContentMedia

        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Retention test"
        )
        ContentMedia.objects.create(
            content_post=cp, r2_key="videos/fail_retain.mp4", file_type="video", order=0
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.FAILED,
            error_message="Account disconnected",
        )

        mock_delete = mocker.patch("utils.r2_storage.R2StorageService.delete_file")

        PostingService.cleanup_r2_media(cp)

        # Media should be retained
        mock_delete.assert_not_called()

    def test_cleanup_r2_media_deletes_when_all_succeeded(self, user, brand, mocker):
        """Should delete R2 files immediately when all platforms succeeded."""
        from content.models import ContentMedia

        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Success delete test"
        )
        ContentMedia.objects.create(
            content_post=cp, r2_key="videos/success.mp4", file_type="video", order=0
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.POSTED,
        )

        mock_delete = mocker.patch("utils.r2_storage.R2StorageService.delete_file")

        PostingService.cleanup_r2_media(cp)

        mock_delete.assert_called_once_with("videos/success.mp4")

    def test_cleanup_r2_media_forced_deletes_failed_post_media(
        self, user, brand, mocker
    ):
        """Should delete R2 files on failed post when force=True is passed."""
        from content.models import ContentMedia

        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Force delete test"
        )
        ContentMedia.objects.create(
            content_post=cp, r2_key="videos/force.mp4", file_type="video", order=0
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.FAILED,
        )

        mock_delete = mocker.patch("utils.r2_storage.R2StorageService.delete_file")

        PostingService.cleanup_r2_media(cp, force=True)

        mock_delete.assert_called_once_with("videos/force.mp4")

    def test_cleanup_expired_failed_post_media_respects_scheduled_post(
        self, user, brand, mocker
    ):
        """A post created weeks ago that failed recently must NOT be deleted."""
        from datetime import timedelta

        from django.utils import timezone

        from content.models import ContentMedia
        from content.tasks import cleanup_expired_failed_post_media

        now = timezone.now()
        # Created 30 days ago, scheduled for yesterday, failed yesterday
        cp = ContentPost.objects.create(
            user=user,
            brand=brand,
            caption="Scheduled old post",
            scheduled_at=now - timedelta(days=1),
        )
        ContentPost.objects.filter(id=cp.id).update(created_at=now - timedelta(days=30))
        media = ContentMedia.objects.create(
            content_post=cp, r2_key="videos/scheduled.mp4", file_type="video", order=0
        )
        entry = ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.FAILED,
        )
        # Failure updated yesterday (well within 7 days)
        ContentPostPlatform.objects.filter(id=entry.id).update(
            updated_at=now - timedelta(days=1)
        )

        mock_delete = mocker.patch("utils.r2_storage.R2StorageService.delete_file")

        cleanup_expired_failed_post_media()

        # Should NOT be deleted because it failed only 1 day ago!
        mock_delete.assert_not_called()

    def test_cleanup_expired_failed_post_media_deletes_after_retention_window(
        self, user, brand, mocker
    ):
        """A post whose failure is older than retention window (8 days ago) is deleted."""
        from datetime import timedelta

        from django.utils import timezone

        from content.models import ContentMedia
        from content.tasks import cleanup_expired_failed_post_media

        now = timezone.now()
        cp = ContentPost.objects.create(
            user=user,
            brand=brand,
            caption="Truly expired post",
        )
        media = ContentMedia.objects.create(
            content_post=cp, r2_key="videos/expired.mp4", file_type="video", order=0
        )
        entry = ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.FAILED,
        )
        # Failure was 8 days ago
        ContentPostPlatform.objects.filter(id=entry.id).update(
            updated_at=now - timedelta(days=8)
        )

        mock_delete = mocker.patch("utils.r2_storage.R2StorageService.delete_file")

        cleanup_expired_failed_post_media()

        # Should be deleted
        mock_delete.assert_called_once_with("videos/expired.mp4")


class TestFrontendUrls:
    def test_frontend_urls_build_correctly(self):
        """FrontendUrls should build clean, typed routes using FRONTEND_URL."""
        from utils.frontend_urls import FrontendUrls

        assert FrontendUrls.base() == "https://postglee.com"
        assert FrontendUrls.dashboard() == "https://postglee.com/dashboard"
        assert FrontendUrls.post_detail("123") == "https://postglee.com/posts/123"
        assert FrontendUrls.retry_post("123") == "https://postglee.com/posts/123/retry"
        assert (
            FrontendUrls.social_connections()
            == "https://postglee.com/settings/connections"
        )
        assert FrontendUrls.login() == "https://postglee.com/login"
        assert (
            FrontendUrls.password_reset("xyz")
            == "https://postglee.com/reset-password?token=xyz"
        )


class TestContentPostSelector:
    def test_selector_get_methods(self, user, brand):
        """ContentPostSelector should retrieve posts cleanly for user and by ID."""
        from content.selectors import ContentPostSelector

        cp = ContentPost.objects.create(
            user=user, brand=brand, caption="Selector test", content_type="video"
        )
        ContentPostPlatform.objects.create(
            content_post=cp,
            platform=PlatformChoices.INSTAGRAM,
            status=PostStatus.POSTED,
        )

        fetched_for_user = ContentPostSelector.get_content_post(cp.id, user)
        assert fetched_for_user.id == cp.id

        fetched_by_id = ContentPostSelector.get_content_post_by_id(cp.id)
        assert fetched_by_id.id == cp.id
        assert fetched_by_id.user == user
        assert fetched_by_id.brand == brand

    def test_selector_has_pending_entries(self, user, brand):
        """ContentPostSelector.has_pending_entries should reflect active states."""
        from content.selectors import ContentPostSelector

        cp = ContentPost.objects.create(user=user, brand=brand, caption="Pending check")
        entry = ContentPostPlatform.objects.create(
            content_post=cp, platform=PlatformChoices.TIKTOK, status=PostStatus.PENDING
        )
        assert ContentPostSelector.has_pending_entries(cp) is True

        entry.status = PostStatus.POSTED
        entry.save(update_fields=["status"])
        assert ContentPostSelector.has_pending_entries(cp) is False
