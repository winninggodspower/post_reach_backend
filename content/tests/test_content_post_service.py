"""
Tests for ContentPostService — the model query service layer.
"""

import uuid

import pytest
from django.utils import timezone

from content.enums import PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from content.services.content_post_service import ContentPostService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount


class TestGetContentPost:
    """Tests for ContentPostService.get_content_post()"""

    def test_retrieves_own_post(self, db, user, brand):
        """Should return the post when the user owns it."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="My Post", content_type="video"
        )

        result = ContentPostService.get_content_post(post.id, user)
        assert result.id == post.id
        assert result.caption == "My Post"
        assert result.brand == brand

    def test_prefetches_media_items(self, db, user, brand):
        """Should prefetch media_items to avoid N+1 queries."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="With Media", content_type="photo"
        )
        ContentMedia.objects.create(
            content_post=post, r2_key="photos/a.jpg", file_type="image", order=0
        )
        ContentMedia.objects.create(
            content_post=post, r2_key="photos/b.jpg", file_type="image", order=1
        )

        result = ContentPostService.get_content_post(post.id, user)
        # Access media_items after retrieval — should use prefetched cache
        items = list(result.media_items.all())
        assert len(items) == 2

    def test_prefetches_platform_entries(self, db, user, brand):
        """Should prefetch platform_entries to avoid N+1 queries."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="With Platforms", content_type="video"
        )
        ContentPostPlatform.objects.create(
            content_post=post, platform=PlatformChoices.YOUTUBE
        )
        ContentPostPlatform.objects.create(
            content_post=post, platform=PlatformChoices.FACEBOOK
        )

        result = ContentPostService.get_content_post(post.id, user)
        entries = list(result.platform_entries.all())
        assert len(entries) == 2

    def test_raises_does_not_exist_for_other_user(self, db, user, brand):
        """Should raise DoesNotExist when a different user requests the post."""
        from users.models import User

        other_user = User.objects.create_user(
            email="other@example.com",
            password="Pass1234!",
            first_name="O",
            last_name="T",
            handle="othertest",
        )

        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Secret Post", content_type="video"
        )

        with pytest.raises(ContentPost.DoesNotExist):
            ContentPostService.get_content_post(post.id, other_user)

    def test_raises_does_not_exist_for_random_uuid(self, db, user, brand):
        """Should raise DoesNotExist for a non-existent post ID."""
        with pytest.raises(ContentPost.DoesNotExist):
            ContentPostService.get_content_post(uuid.uuid4(), user)


class TestGetMediaItems:
    """Tests for ContentPostService.get_media_items()"""

    def test_returns_filtered_by_file_type(self, db, user, brand):
        """Should return only items matching the requested file_type."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Mixed Media", content_type="video"
        )
        v1 = ContentMedia.objects.create(
            content_post=post, r2_key="videos/a.mp4", file_type="video", order=0
        )
        ContentMedia.objects.create(
            content_post=post, r2_key="photos/thumb.jpg", file_type="image", order=1
        )
        v2 = ContentMedia.objects.create(
            content_post=post, r2_key="videos/b.mp4", file_type="video", order=2
        )

        videos = list(ContentPostService.get_media_items(post, file_type="video"))
        assert len(videos) == 2
        assert videos[0].id == v1.id
        assert videos[1].id == v2.id

    def test_returns_ordered_by_order_field(self, db, user, brand):
        """Should return media items in ascending order by the order field."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Ordered", content_type="photo"
        )
        second = ContentMedia.objects.create(
            content_post=post, r2_key="photos/b.jpg", file_type="image", order=1
        )
        first = ContentMedia.objects.create(
            content_post=post, r2_key="photos/a.jpg", file_type="image", order=0
        )
        third = ContentMedia.objects.create(
            content_post=post, r2_key="photos/c.jpg", file_type="image", order=2
        )

        items = list(ContentPostService.get_media_items(post, file_type="image"))
        assert items[0].id == first.id
        assert items[1].id == second.id
        assert items[2].id == third.id

    def test_returns_empty_queryset_when_no_match(self, db, user, brand):
        """Should return empty list when no items match the file_type."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Empty", content_type="video"
        )
        ContentMedia.objects.create(
            content_post=post, r2_key="videos/a.mp4", file_type="video", order=0
        )

        images = list(ContentPostService.get_media_items(post, file_type="image"))
        assert len(images) == 0


class TestHasPendingEntries:
    """Tests for ContentPostService.has_pending_entries()"""

    def test_returns_true_when_pending_exists(self, db, user, brand):
        """Should return True if any platform entry is in PENDING status."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Pending", content_type="video"
        )
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.POSTED,
        )
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.PENDING,
        )

        assert ContentPostService.has_pending_entries(post) is True

    def test_returns_true_when_uploading_exists(self, db, user, brand):
        """Should return True if any platform entry is in UPLOADING status."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Uploading", content_type="video"
        )
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.UPLOADING,
        )

        assert ContentPostService.has_pending_entries(post) is True

    def test_returns_false_when_all_finished(self, db, user, brand):
        """Should return False when all entries are POSTED or FAILED."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Finished", content_type="video"
        )
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.POSTED,
        )
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.FAILED,
        )

        assert ContentPostService.has_pending_entries(post) is False

    def test_returns_false_when_no_entries(self, db, user, brand):
        """Should return False when there are no platform entries at all."""
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="No Entries", content_type="video"
        )

        assert ContentPostService.has_pending_entries(post) is False
