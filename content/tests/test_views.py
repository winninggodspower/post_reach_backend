"""
Integration tests for ContentPostViewSet endpoints:
  POST /api/content/posts/video/
  POST /api/content/posts/photo/
"""

import io
import json

import pytest
from django.urls import reverse
from django.utils import timezone

from content.enums import PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount


class TestRetrieveEndpoint:
    """Tests for GET /api/content/posts/{id}/"""

    def test_retrieve_own_post(self, db, authenticated_client, user, brand, mocker):
        content_post = ContentPost.objects.create(
            user=user, brand=brand, caption="Status Check", content_type="video"
        )
        ContentMedia.objects.create(
            content_post=content_post, r2_key="videos/k.mp4", file_type="video", order=0
        )
        ContentPostPlatform.objects.create(
            content_post=content_post,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.POSTED,
            platform_post_id="yt_001",
        )
        ContentPostPlatform.objects.create(
            content_post=content_post,
            platform=PlatformChoices.FACEBOOK,
            status=PostStatus.PENDING,
        )

        from django.urls import reverse

        url = reverse("content-post-detail", kwargs={"pk": content_post.id})
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.data
        assert data["success"] is True
        assert data["data"]["caption"] == "Status Check"
        assert len(data["data"]["platforms"]) == 2
        statuses = {(p["platform"], p["status"]) for p in data["data"]["platforms"]}
        assert ("youtube", "posted") in statuses
        assert ("facebook", "pending") in statuses

    def test_retrieve_other_users_post_returns_404(self, db, api_client, mocker):
        from users.models import User

        owner = User.objects.create_user(
            email="owner@example.com",
            password="Pass1234!",
            first_name="O",
            last_name="W",
            handle="owner",
        )
        from users.models import Brand as BrandModel

        brand = BrandModel.objects.filter(user=owner, is_default=True).first()
        if not brand:
            brand = BrandModel.objects.create(
                user=owner, name="OwnerBrand", is_default=True
            )

        content_post = ContentPost.objects.create(
            user=owner, brand=brand, caption="Other's Post", content_type="video"
        )
        ContentMedia.objects.create(
            content_post=content_post, r2_key="videos/o.mp4", file_type="video", order=0
        )
        ContentPostPlatform.objects.create(
            content_post=content_post,
            platform=PlatformChoices.YOUTUBE,
            status=PostStatus.POSTED,
        )

        # Authenticate as a different user
        other = User.objects.create_user(
            email="other@example.com",
            password="Pass1234!",
            first_name="O",
            last_name="T",
            handle="otheruser",
        )
        from users.models import Brand as OtherBrand

        OtherBrand.objects.filter(user=other).delete()  # clean up auto-created brand
        api_client.force_authenticate(user=other)

        from django.urls import reverse

        url = reverse("content-post-detail", kwargs={"pk": content_post.id})
        response = api_client.get(url)

        assert response.status_code == 404

    def test_retrieve_not_found(self, db, authenticated_client, user, brand):
        import uuid

        from django.urls import reverse

        url = reverse("content-post-detail", kwargs={"pk": uuid.uuid4()})
        response = authenticated_client.get(url)
        assert response.status_code == 404


class TestPresignedUrlEndpoint:
    """Integration tests for POST /api/content/posts/presigned-url/"""

    URL = "content-post-presigned-url"

    def test_success_single_file(self, db, authenticated_client, mocker):
        mocker.patch(
            "content.views.R2StorageService.generate_presigned_upload_url",
            return_value={"key": "videos/test.mp4", "url": "https://fake-url.com/"},
        )
        from django.urls import reverse

        response = authenticated_client.post(
            reverse(self.URL),
            {"files": [{"content_type": "video", "extension": "mp4"}]},
            format="json",
        )

        assert response.status_code == 200
        data = response.data
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["key"] == "videos/test.mp4"
        assert data["data"][0]["url"] == "https://fake-url.com/"

    def test_success_multiple_files(self, db, authenticated_client, mocker):
        mocker.patch(
            "content.views.R2StorageService.generate_presigned_upload_url",
            side_effect=[
                {"key": "photos/1.jpg", "url": "https://url1.com/"},
                {"key": "photos/2.jpg", "url": "https://url2.com/"},
            ],
        )
        from django.urls import reverse

        response = authenticated_client.post(
            reverse(self.URL),
            {
                "files": [
                    {"content_type": "photo", "extension": "jpg"},
                    {"content_type": "photo", "extension": "jpg"},
                ]
            },
            format="json",
        )

        assert response.status_code == 200
        data = response.data
        assert len(data["data"]) == 2
        assert data["data"][0]["key"] == "photos/1.jpg"
        assert data["data"][1]["key"] == "photos/2.jpg"

    def test_invalid_content_type(self, db, authenticated_client):
        from django.urls import reverse

        response = authenticated_client.post(
            reverse(self.URL),
            {"files": [{"content_type": "document"}]},
            format="json",
        )
        assert response.status_code == 400


class TestVideoEndpoint:
    """Integration tests for POST /api/content/posts/video/"""

    URL = "content-post-video"

    def test_success_single_platform(
        self, db, authenticated_client, user, brand, mocker
    ):
        mocker.patch(
            "content.services.content_post_service.transaction.on_commit",
            side_effect=lambda f: f(),
        )
        mocker.patch(
            "content.services.content_post_service.R2StorageService.generate_key",
            return_value="videos/2026-06-15/abc.mp4",
        )
        mock_delay = mocker.patch(
            "content.tasks.wait_for_media_and_publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.YOUTUBE,
            account_name="ch",
            external_id="ext",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )

        response = authenticated_client.post(
            reverse(self.URL),
            {
                "video_key": "videos/2026-06-15/abc.mp4",
                "caption": "Test Video",
                "platforms": [PlatformChoices.YOUTUBE],
                "platform_settings": json.dumps(
                    {"youtube": {"title": "YouTube Title"}}
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201
        data = response.data
        assert data["success"] is True
        assert len(data["data"]["platforms"]) == 1
        assert data["data"]["platforms"][0]["platform"] == PlatformChoices.YOUTUBE
        # Verify a ContentMedia record was created
        post = ContentPost.objects.get(id=data["data"]["id"])
        assert post.media_items.count() == 1
        assert post.media_items.first().file_type == "video"
        mock_delay.assert_called_once()

    def test_success_multiple_platforms(
        self, db, authenticated_client, user, brand, mocker
    ):
        mocker.patch(
            "content.services.content_post_service.transaction.on_commit",
            side_effect=lambda f: f(),
        )
        mocker.patch(
            "content.services.content_post_service.R2StorageService.generate_key",
            return_value="videos/2026-06-15/m.mp4",
        )
        mock_delay = mocker.patch(
            "content.tasks.wait_for_media_and_publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        for plat in [PlatformChoices.YOUTUBE, PlatformChoices.FACEBOOK]:
            SocialAccount.objects.create(
                brand=brand,
                platform=plat,
                account_name=f"a_{plat}",
                external_id=f"e_{plat}",
                access_token=f"t_{plat}",
                token_type="Bearer",
                token_expires_at=expires,
            )

        response = authenticated_client.post(
            reverse(self.URL),
            {
                "video_key": "videos/2026-06-15/m.mp4",
                "caption": "Multi",
                "platforms": [PlatformChoices.YOUTUBE, PlatformChoices.FACEBOOK],
                "platform_settings": json.dumps(
                    {"youtube": {"title": "YouTube Title"}}
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201
        assert len(response.data["data"]["platforms"]) == 2
        assert mock_delay.call_count == 2

    def test_no_default_brand(self, db, api_client, mocker):
        from users.models import Brand, User

        user = User.objects.create_user(
            email="nb@example.com",
            password="P@ss1234!",
            first_name="X",
            last_name="Y",
            handle="nobrand",
        )
        Brand.objects.filter(user=user).delete()
        api_client.force_authenticate(user=user)

        response = api_client.post(
            reverse(self.URL),
            {
                "video_key": "videos/2026-06-15/m.mp4",
                "caption": "Test",
                "platforms": [PlatformChoices.YOUTUBE],
                "platform_settings": json.dumps(
                    {"youtube": {"title": "YouTube Title"}}
                ),
            },
            format="multipart",
        )
        assert response.status_code == 400
        assert "No default brand" in response.data.get("message", "")

    def test_success_with_thumbnail(
        self, db, authenticated_client, user, brand, mocker
    ):
        mocker.patch(
            "content.services.content_post_service.transaction.on_commit",
            side_effect=lambda f: f(),
        )
        mocker.patch(
            "content.services.content_post_service.R2StorageService.generate_key",
            side_effect=["videos/abc.mp4", "photos/thumb.jpg"],
        )
        mocker.patch(
            "content.serializers.R2StorageService.generate_presigned_url",
            return_value="https://r2-presigned-url.com/thumb.jpg",
        )
        mock_delay = mocker.patch(
            "content.tasks.wait_for_media_and_publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.YOUTUBE,
            account_name="ch",
            external_id="ext",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )

        response = authenticated_client.post(
            reverse(self.URL),
            {
                "video_key": "videos/abc.mp4",
                "thumbnail_key": "photos/thumb.jpg",
                "video_thumbnail_offset": 5000,
                "caption": "Test Video",
                "platforms": [PlatformChoices.YOUTUBE],
                "platform_settings": json.dumps(
                    {"youtube": {"title": "YouTube Title"}}
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201
        data = response.data
        assert data["success"] is True
        assert data["data"]["thumbnail_url"] == "https://r2-presigned-url.com/thumb.jpg"
        assert data["data"]["video_thumbnail_offset"] == 5000

        # Verify a ContentPost record was created with the correct properties
        post = ContentPost.objects.get(id=data["data"]["id"])
        assert post.thumbnail_r2_key == "photos/thumb.jpg"
        assert post.video_thumbnail_offset == 5000
        mock_delay.assert_called_once()

    def test_unauthenticated(self, db):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(reverse(self.URL), {}, format="multipart")
        assert response.status_code == 401


class TestPhotoEndpoint:
    """Integration tests for POST /api/content/posts/photo/"""

    URL = "content-post-photo"

    def test_success_single_photo(self, db, authenticated_client, user, brand, mocker):
        mocker.patch(
            "content.services.content_post_service.transaction.on_commit",
            side_effect=lambda f: f(),
        )
        mocker.patch(
            "content.services.content_post_service.R2StorageService.generate_key",
            return_value="photos/2026-06-15/p.jpg",
        )
        mock_delay = mocker.patch(
            "content.tasks.wait_for_media_and_publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.INSTAGRAM,
            account_name="ig",
            external_id="ext_ig",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )

        response = authenticated_client.post(
            reverse(self.URL),
            {
                "photo_keys": ["photos/2026-06-15/p.jpg"],
                "caption": "Nice shot",
                "platforms": [PlatformChoices.INSTAGRAM],
            },
            format="multipart",
        )

        assert response.status_code == 201
        data = response.data
        assert data["success"] is True
        assert len(data["data"]["platforms"]) == 1
        assert data["data"]["platforms"][0]["platform"] == PlatformChoices.INSTAGRAM
        # Verify a ContentMedia record was created
        post = ContentPost.objects.get(id=data["data"]["id"])
        assert post.media_items.count() == 1
        assert post.media_items.first().file_type == "image"
        mock_delay.assert_called_once()

    def test_success_multiple_photos(
        self, db, authenticated_client, user, brand, mocker
    ):
        mocker.patch(
            "content.services.content_post_service.transaction.on_commit",
            side_effect=lambda f: f(),
        )
        mocker.patch(
            "content.services.content_post_service.R2StorageService.generate_key",
            side_effect=[
                "photos/2026-06-15/a.jpg",
                "photos/2026-06-15/b.jpg",
            ],
        )
        mock_delay = mocker.patch(
            "content.tasks.wait_for_media_and_publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.FACEBOOK,
            account_name="fb",
            external_id="ext_fb",
            access_token="token",
            token_type="Bearer",
            token_expires_at=expires,
        )

        response = authenticated_client.post(
            reverse(self.URL),
            {
                "photo_keys": ["photos/2026-06-15/a.jpg", "photos/2026-06-15/b.jpg"],
                "caption": "Multi photo",
                "platforms": [PlatformChoices.FACEBOOK],
            },
            format="multipart",
        )

        assert response.status_code == 201
        data = response.data
        assert data["success"] is True
        # Verify 2 ContentMedia records were created
        post = ContentPost.objects.get(id=data["data"]["id"])
        assert post.media_items.count() == 2
        items = list(post.media_items.order_by("order"))
        assert items[0].order == 0
        assert items[1].order == 1
        mock_delay.assert_called_once()

    def test_no_connected_account(self, db, authenticated_client, user, brand, mocker):
        response = authenticated_client.post(
            reverse(self.URL),
            {
                "photo_keys": ["photos/2026-06-15/p.jpg"],
                "caption": "Test",
                "platforms": [PlatformChoices.INSTAGRAM],
            },
            format="multipart",
        )
        assert response.status_code == 400
        assert "No connected account" in response.data.get("message", "")

    def test_unauthenticated(self, db):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(reverse(self.URL), {}, format="multipart")
        assert response.status_code == 401

    def test_expired_connection_raises_error(
        self, db, authenticated_client, user, brand, mocker
    ):
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.INSTAGRAM,
            account_name="ig_expired",
            external_id="ext_ig_expired",
            access_token="token",
            token_type="Bearer",
            token_expires_at=timezone.now() - timezone.timedelta(days=1),
        )

        response = authenticated_client.post(
            reverse(self.URL),
            {
                "photo_keys": ["photos/2026-06-15/p.jpg"],
                "caption": "Test",
                "platforms": [PlatformChoices.INSTAGRAM],
            },
            format="multipart",
        )
        assert response.status_code == 400
        assert "have expired" in response.data.get("message", "")
