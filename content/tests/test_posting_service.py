"""
Unit tests for PostingService (video + photo), ContentCreationService,
and serializer validation.
"""

from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from content.enums import PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from content.serializers import (
    ContentPostCreateSerializer,
    PhotoPostCreateSerializer,
)
from content.services.content_creation_service import ContentCreationService
from content.services.posting_service import PostingService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount


class TestContentPostCreateSerializer:
    """Tests for video serializer."""

    def test_valid_single_platform(self):
        data = {
            "video": MagicMock(),
            "title": "My Test Video",
            "platforms": [PlatformChoices.YOUTUBE],
        }
        serializer = ContentPostCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_valid_multiple_platforms(self):
        data = {
            "video": MagicMock(),
            "title": "My Test Video",
            "platforms": [PlatformChoices.YOUTUBE, PlatformChoices.FACEBOOK],
        }
        serializer = ContentPostCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_title(self):
        data = {
            "video": MagicMock(),
            "platforms": [PlatformChoices.YOUTUBE],
        }
        serializer = ContentPostCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "title" in serializer.errors


class TestPhotoPostCreateSerializer:
    """Tests for photo serializer."""

    def test_valid(self):
        data = {
            "photos": [MagicMock()],
            "text": "A beautiful photo",
            "platforms": [PlatformChoices.INSTAGRAM],
        }
        serializer = PhotoPostCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_valid_multiple_photos(self):
        data = {
            "photos": [MagicMock(), MagicMock()],
            "text": "Multi photo post",
            "platforms": [PlatformChoices.FACEBOOK],
        }
        serializer = PhotoPostCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_text_optional(self):
        data = {
            "photos": [MagicMock()],
            "platforms": [PlatformChoices.FACEBOOK],
        }
        serializer = PhotoPostCreateSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data.get("text") == ""

    def test_missing_photos(self):
        data = {
            "text": "Missing photos",
            "platforms": [PlatformChoices.INSTAGRAM],
        }
        serializer = PhotoPostCreateSerializer(data=data)
        assert not serializer.is_valid()


class TestContentCreationService:
    """Tests for ContentCreationService.create_content_post() — includes Celery dispatch."""

    def _setup_accounts(self, brand, platforms):
        expires = timezone.now() + timezone.timedelta(days=30)
        for plat in platforms:
            SocialAccount.objects.create(
                brand=brand,
                platform=plat,
                account_name=f"acct_{plat}",
                external_id=f"ext_{plat}",
                access_token=f"token_{plat}",
                token_type="Bearer",
                token_expires_at=expires,
            )

    def _mock_file(self, name="v.mp4", content=b"fake-media"):
        mock_file = MagicMock()
        mock_file.read.return_value = content
        mock_file.name = name
        return mock_file

    def test_create_with_single_platform(self, db, user, brand, mocker):
        mock_upload = mocker.patch(
            "content.services.content_creation_service.R2StorageService.upload_file",
        )
        mocker.patch(
            "content.services.content_creation_service.R2StorageService.generate_key",
            return_value="videos/2026-01-01/abc.mp4",
        )
        mock_delay = mocker.patch(
            "content.tasks.publish_platform_entry.delay",
        )
        self._setup_accounts(brand, [PlatformChoices.YOUTUBE])

        content_post = ContentCreationService.create_content_post(
            user=user,
            media_files=[self._mock_file()],
            text="Hello world",
            platforms=[PlatformChoices.YOUTUBE],
        )

        assert content_post.title == "Hello world"
        # Should have 1 ContentMedia record for the video
        assert content_post.media_items.count() == 1
        assert content_post.media_items.first().file_type == "video"
        assert content_post.platform_entries.count() == 1
        assert content_post.platform_entries.first().platform == PlatformChoices.YOUTUBE
        mock_delay.assert_called_once()

    def test_create_with_multiple_photos(self, db, user, brand, mocker):
        mock_upload = mocker.patch(
            "content.services.content_creation_service.R2StorageService.upload_file",
        )
        mocker.patch(
            "content.services.content_creation_service.R2StorageService.generate_key",
            side_effect=[
                "photos/2026-01-01/a.jpg",
                "photos/2026-01-01/b.jpg",
                "photos/2026-01-01/c.jpg",
            ],
        )
        mock_delay = mocker.patch(
            "content.tasks.publish_platform_entry.delay",
        )
        self._setup_accounts(brand, [PlatformChoices.FACEBOOK, PlatformChoices.INSTAGRAM])

        content_post = ContentCreationService.create_content_post(
            user=user,
            media_files=[
                self._mock_file(name="a.jpg", content=b"photo-a"),
                self._mock_file(name="b.jpg", content=b"photo-b"),
                self._mock_file(name="c.jpg", content=b"photo-c"),
            ],
            text="Multi photo",
            platforms=[PlatformChoices.FACEBOOK, PlatformChoices.INSTAGRAM],
            content_type="photo",
        )

        assert content_post.media_items.count() == 3
        # Check ordering
        items = list(content_post.media_items.order_by("order"))
        assert items[0].order == 0
        assert items[1].order == 1
        assert items[2].order == 2
        assert content_post.platform_entries.count() == 2
        assert mock_delay.call_count == 2
        assert mock_upload.call_count == 3

    def test_create_multiple_dispatches_one_task_per_platform(self, db, user, brand, mocker):
        mock_upload = mocker.patch(
            "content.services.content_creation_service.R2StorageService.upload_file",
        )
        mocker.patch(
            "content.services.content_creation_service.R2StorageService.generate_key",
            return_value="videos/2026-01-01/abc.mp4",
        )
        mock_delay = mocker.patch(
            "content.tasks.publish_platform_entry.delay",
        )
        self._setup_accounts(brand, [PlatformChoices.YOUTUBE, PlatformChoices.FACEBOOK])

        content_post = ContentCreationService.create_content_post(
            user=user,
            media_files=[self._mock_file()],
            text="Multi",
            platforms=[PlatformChoices.YOUTUBE, PlatformChoices.FACEBOOK],
        )

        assert content_post.platform_entries.count() == 2
        assert mock_delay.call_count == 2

    def test_raises_when_no_brand(self, db, user, mocker):
        from users.models import Brand
        Brand.objects.filter(user=user).delete()
        with pytest.raises(ValueError, match="No default brand"):
            ContentCreationService.create_content_post(
                user=user,
                media_files=[self._mock_file()],
                text="Test",
                platforms=[PlatformChoices.YOUTUBE],
            )

    def test_raises_when_platform_not_connected(self, db, user, brand, mocker):
        with pytest.raises(ValueError, match="No connected account"):
            ContentCreationService.create_content_post(
                user=user,
                media_files=[self._mock_file()],
                text="Test",
                platforms=[PlatformChoices.YOUTUBE],
            )


class TestPostingService:
    """Tests for PostingService.publish_platform_entry() (video + photo)."""

    def _setup(self, user, brand, platform, file_type="video"):
        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=platform,
            account_name=f"acct_{platform}",
            external_id=f"ext_{platform}",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )
        content_post = ContentPost.objects.create(
            user=user, brand=brand, title="Test", content_type=file_type
        )
        ContentMedia.objects.create(
            content_post=content_post,
            r2_key=f"{file_type}s/k.{'mp4' if file_type == 'video' else 'jpg'}",
            file_type=file_type,
            order=0,
        )
        entry = ContentPostPlatform.objects.create(
            content_post=content_post, platform=platform
        )
        return entry

    def test_publish_video_success(self, db, user, brand, mocker):
        mock_pub = mocker.patch(
            "content.services.posting_service.YoutubeService.publish_video",
            return_value={"platform_post_id": "yt_123"},
        )
        mocker.patch(
            "content.services.posting_service.R2StorageService.generate_presigned_url",
            return_value="https://r2/v.mp4",
        )
        mocker.patch(
            "content.services.posting_service.R2StorageService.download_file",
            return_value=b"vid",
        )
        entry = self._setup(user, brand, PlatformChoices.YOUTUBE)

        result = PostingService.publish_platform_entry(entry, content_type="video")
        assert result.status == PostStatus.POSTED
        assert result.platform_post_id == "yt_123"

    def test_publish_photo_success_single(self, db, user, brand, mocker):
        mock_pub = mocker.patch(
            "content.services.posting_service.FacebookService.publish_photo",
            return_value={"platform_post_id": "fb_456"},
        )
        mocker.patch(
            "content.services.posting_service.R2StorageService.generate_presigned_url",
            return_value="https://r2/photo.jpg",
        )
        entry = self._setup(user, brand, PlatformChoices.FACEBOOK, file_type="image")

        result = PostingService.publish_platform_entry(entry, content_type="photo")
        assert result.status == PostStatus.POSTED
        assert result.platform_post_id == "fb_456"
        mock_pub.assert_called_once()

    def test_publish_photo_success_multiple(self, db, user, brand, mocker):
        """Test multiple images are passed as a list to the provider."""
        mock_pub = mocker.patch(
            "content.services.posting_service.FacebookService.publish_photo",
            return_value={"platform_post_id": "fb_multi"},
        )
        mocker.patch(
            "content.services.posting_service.R2StorageService.generate_presigned_url",
            return_value="https://r2/photo.jpg",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand, platform=PlatformChoices.FACEBOOK,
            account_name="acct_fb", external_id="ext_fb",
            access_token="token", token_type="Bearer", token_expires_at=expires,
        )
        content_post = ContentPost.objects.create(
            user=user, brand=brand, title="Multi Photo", content_type="photo"
        )
        ContentMedia.objects.create(content_post=content_post, r2_key="photos/a.jpg", file_type="image", order=0)
        ContentMedia.objects.create(content_post=content_post, r2_key="photos/b.jpg", file_type="image", order=1)
        ContentMedia.objects.create(content_post=content_post, r2_key="photos/c.jpg", file_type="image", order=2)
        entry = ContentPostPlatform.objects.create(
            content_post=content_post, platform=PlatformChoices.FACEBOOK
        )

        result = PostingService.publish_platform_entry(entry, content_type="photo")
        assert result.status == PostStatus.POSTED
        # Verify 3 URLs were generated and passed
        assert mock_pub.call_count == 1
        call_args = mock_pub.call_args
        assert len(call_args.kwargs["photo_urls"]) == 3

    def test_publish_failure(self, db, user, brand, mocker):
        mocker.patch(
            "content.services.posting_service.YoutubeService.publish_video",
            side_effect=ValueError("API down"),
        )
        mocker.patch(
            "content.services.posting_service.R2StorageService.generate_presigned_url",
            return_value="https://r2/v.mp4",
        )
        mocker.patch(
            "content.services.posting_service.R2StorageService.download_file",
            return_value=b"vid",
        )
        entry = self._setup(user, brand, PlatformChoices.YOUTUBE)

        result = PostingService.publish_platform_entry(entry, content_type="video")
        assert result.status == PostStatus.FAILED
        assert result.error_message == "API down"

    def test_cleanup_when_all_finished(self, db, user, brand, mocker):
        mock_delete = mocker.patch(
            "content.services.posting_service.R2StorageService.delete_file",
            return_value=True,
        )
        cp = ContentPost.objects.create(
            user=user, brand=brand, title="C", content_type="video"
        )
        ContentMedia.objects.create(content_post=cp, r2_key="videos/k.mp4", file_type="video", order=0)
        ContentMedia.objects.create(content_post=cp, r2_key="videos/thumb.jpg", file_type="image", order=1)
        ContentPostPlatform.objects.create(
            content_post=cp, platform=PlatformChoices.YOUTUBE, status=PostStatus.POSTED
        )
        ContentPostPlatform.objects.create(
            content_post=cp, platform=PlatformChoices.FACEBOOK, status=PostStatus.FAILED
        )
        PostingService.cleanup_r2_media(cp)
        # Should delete both media items
        assert mock_delete.call_count == 2

    def test_cleanup_skips_when_pending(self, db, user, brand, mocker):
        mock_delete = mocker.patch(
            "content.services.posting_service.R2StorageService.delete_file",
        )
        cp = ContentPost.objects.create(
            user=user, brand=brand, title="P", content_type="video"
        )
        ContentMedia.objects.create(content_post=cp, r2_key="videos/k.mp4", file_type="video", order=0)
        ContentPostPlatform.objects.create(
            content_post=cp, platform=PlatformChoices.YOUTUBE, status=PostStatus.POSTED
        )
        ContentPostPlatform.objects.create(
            content_post=cp, platform=PlatformChoices.FACEBOOK, status=PostStatus.PENDING
        )
        PostingService.cleanup_r2_media(cp)
        mock_delete.assert_not_called()