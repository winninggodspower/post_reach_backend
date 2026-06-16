"""
Integration tests for ContentPostViewSet endpoints:
  POST /api/content/posts/video/
  POST /api/content/posts/photo/
"""

import io

import pytest
from django.urls import reverse

from content.enums import PostStatus
from content.models import ContentPost, ContentPostPlatform
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount
from django.utils import timezone


class TestRetrieveEndpoint:
    """Tests for GET /api/content/posts/{id}/"""

    def test_retrieve_own_post(self, db, authenticated_client, user, brand, mocker):
        content_post = ContentPost.objects.create(
            user=user, brand=brand, title="Status Check", media_r2_key="videos/k.mp4"
        )
        ContentPostPlatform.objects.create(
            content_post=content_post, platform=PlatformChoices.YOUTUBE, status=PostStatus.POSTED, platform_post_id="yt_001"
        )
        ContentPostPlatform.objects.create(
            content_post=content_post, platform=PlatformChoices.FACEBOOK, status=PostStatus.PENDING
        )

        from django.urls import reverse
        url = reverse("content-post-detail", kwargs={"pk": content_post.id})
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.data
        assert data["success"] is True
        assert data["data"]["title"] == "Status Check"
        assert len(data["data"]["platforms"]) == 2
        statuses = {(p["platform"], p["status"]) for p in data["data"]["platforms"]}
        assert ("youtube", "posted") in statuses
        assert ("facebook", "pending") in statuses

    def test_retrieve_other_users_post_returns_404(self, db, api_client, mocker):
        from users.models import User
        owner = User.objects.create_user(
            email="owner@example.com", password="Pass1234!",
            first_name="O", last_name="W", handle="owner",
        )
        from users.models import Brand as BrandModel
        brand = BrandModel.objects.filter(user=owner, is_default=True).first()
        if not brand:
            brand = BrandModel.objects.create(user=owner, name="OwnerBrand", is_default=True)

        content_post = ContentPost.objects.create(
            user=owner, brand=brand, title="Other's Post", media_r2_key="videos/o.mp4"
        )
        ContentPostPlatform.objects.create(
            content_post=content_post, platform=PlatformChoices.YOUTUBE, status=PostStatus.POSTED
        )

        # Authenticate as a different user
        other = User.objects.create_user(
            email="other@example.com", password="Pass1234!",
            first_name="O", last_name="T", handle="otheruser",
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


class TestVideoEndpoint:
    """Integration tests for POST /api/content/posts/video/"""

    URL = "content-post-video"

    def test_success_single_platform(self, db, authenticated_client, user, brand, mocker):
        mock_upload = mocker.patch(
            "content.services.content_creation_service.R2StorageService.upload_file",
        )
        mocker.patch(
            "content.services.content_creation_service.R2StorageService.generate_key",
            return_value="videos/2026-06-15/abc.mp4",
        )
        mock_delay = mocker.patch(
            "content.tasks.publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand, platform=PlatformChoices.YOUTUBE,
            account_name="ch", external_id="ext",
            access_token="token", token_type="Bearer", token_expires_at=expires,
        )

        video = io.BytesIO(b"fake-video")
        video.name = "v.mp4"

        response = authenticated_client.post(
            reverse(self.URL),
            {"video": video, "title": "Test Video", "platforms": [PlatformChoices.YOUTUBE]},
            format="multipart",
        )

        assert response.status_code == 201
        data = response.data
        assert data["success"] is True
        assert len(data["data"]["platforms"]) == 1
        assert data["data"]["platforms"][0]["platform"] == PlatformChoices.YOUTUBE
        mock_upload.assert_called_once()
        mock_delay.assert_called_once()

    def test_success_multiple_platforms(self, db, authenticated_client, user, brand, mocker):
        mocker.patch("content.services.content_creation_service.R2StorageService.upload_file")
        mocker.patch(
            "content.services.content_creation_service.R2StorageService.generate_key",
            return_value="videos/2026-06-15/m.mp4",
        )
        mock_delay = mocker.patch(
            "content.tasks.publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        for plat in [PlatformChoices.YOUTUBE, PlatformChoices.FACEBOOK]:
            SocialAccount.objects.create(
                brand=brand, platform=plat,
                account_name=f"a_{plat}", external_id=f"e_{plat}",
                access_token=f"t_{plat}", token_type="Bearer", token_expires_at=expires,
            )

        video = io.BytesIO(b"v")
        video.name = "v.mp4"

        response = authenticated_client.post(
            reverse(self.URL),
            {"video": video, "title": "Multi", "platforms": [PlatformChoices.YOUTUBE, PlatformChoices.FACEBOOK]},
            format="multipart",
        )

        assert response.status_code == 201
        assert len(response.data["data"]["platforms"]) == 2
        assert mock_delay.call_count == 2

    def test_no_default_brand(self, db, api_client, mocker):
        from users.models import User, Brand
        user = User.objects.create_user(
            email="nb@example.com", password="P@ss1234!",
            first_name="X", last_name="Y", handle="nobrand",
        )
        Brand.objects.filter(user=user).delete()
        api_client.force_authenticate(user=user)

        video = io.BytesIO(b"v")
        video.name = "v.mp4"

        response = api_client.post(
            reverse(self.URL),
            {"video": video, "title": "Test", "platforms": [PlatformChoices.YOUTUBE]},
            format="multipart",
        )
        assert response.status_code == 400
        assert "No default brand" in response.data.get("message", "")

    def test_unauthenticated(self, db):
        from rest_framework.test import APIClient
        client = APIClient()
        response = client.post(reverse(self.URL), {}, format="multipart")
        assert response.status_code == 401


class TestPhotoEndpoint:
    """Integration tests for POST /api/content/posts/photo/"""

    URL = "content-post-photo"

    def test_success(self, db, authenticated_client, user, brand, mocker):
        mock_upload = mocker.patch(
            "content.services.content_creation_service.R2StorageService.upload_file",
        )
        mocker.patch(
            "content.services.content_creation_service.R2StorageService.generate_key",
            return_value="photos/2026-06-15/p.jpg",
        )
        mock_delay = mocker.patch(
            "content.tasks.publish_platform_entry.delay",
        )

        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand, platform=PlatformChoices.INSTAGRAM,
            account_name="ig", external_id="ext_ig",
            access_token="token", token_type="Bearer", token_expires_at=expires,
        )

        photo = io.BytesIO(b"fake-photo")
        photo.name = "p.jpg"

        response = authenticated_client.post(
            reverse(self.URL),
            {"photo": photo, "text": "Nice shot", "platforms": [PlatformChoices.INSTAGRAM]},
            format="multipart",
        )

        assert response.status_code == 201
        data = response.data
        assert data["success"] is True
        assert len(data["data"]["platforms"]) == 1
        assert data["data"]["platforms"][0]["platform"] == PlatformChoices.INSTAGRAM
        mock_upload.assert_called_once()
        mock_delay.assert_called_once()

    def test_no_connected_account(self, db, authenticated_client, user, brand, mocker):
        photo = io.BytesIO(b"p")
        photo.name = "p.jpg"

        response = authenticated_client.post(
            reverse(self.URL),
            {"photo": photo, "text": "Test", "platforms": [PlatformChoices.INSTAGRAM]},
            format="multipart",
        )
        assert response.status_code == 400
        assert "No connected account" in response.data.get("message", "")

    def test_unauthenticated(self, db):
        from rest_framework.test import APIClient
        client = APIClient()
        response = client.post(reverse(self.URL), {}, format="multipart")
        assert response.status_code == 401
