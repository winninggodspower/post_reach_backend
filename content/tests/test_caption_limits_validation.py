import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from content.enums import PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from content.serializers import (
    ContentPostCreateSerializer,
    ContentPostUpdateSerializer,
    PhotoPostCreateSerializer,
    TextPostCreateSerializer,
)
from content.services.content_post_service import ContentPostService
from content.validators import validate_platform_captions
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount


class TestValidatePlatformCaptionsUnit:
    """Direct unit tests for validate_platform_captions validator."""

    def test_threads_valid_length(self):
        errors = validate_platform_captions(
            platforms=[PlatformChoices.THREADS],
            caption="A" * 500,
        )
        assert errors == {}

    def test_threads_general_caption_exceeds_limit(self):
        errors = validate_platform_captions(
            platforms=[PlatformChoices.THREADS],
            caption="A" * 501,
        )
        assert PlatformChoices.THREADS in errors
        assert "500 characters" in errors[PlatformChoices.THREADS]
        assert "501" in errors[PlatformChoices.THREADS]

    def test_threads_platform_override_valid_while_general_caption_exceeds(self):
        errors = validate_platform_captions(
            platforms=[PlatformChoices.THREADS],
            caption="A" * 600,
            platform_settings={"threads": {"caption": "Short Threads caption"}},
        )
        assert errors == {}

    def test_threads_platform_override_exceeds_limit(self):
        errors = validate_platform_captions(
            platforms=[PlatformChoices.THREADS],
            caption="Short",
            platform_settings={"threads": {"caption": "A" * 505}},
        )
        assert PlatformChoices.THREADS in errors
        assert "505" in errors[PlatformChoices.THREADS]

    def test_twitter_standard_account_valid_length(self, brand):
        errors = validate_platform_captions(
            platforms=[PlatformChoices.TWITTER],
            caption="A" * 280,
            brand=brand,
        )
        assert errors == {}

    def test_twitter_standard_account_exceeds_280(self, brand):
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.TWITTER,
            account_name="test_tw",
            external_id="123",
            access_token="tok",
            token_expires_at=timezone.now() + timezone.timedelta(days=30),
            metadata={"is_premium": False},
        )
        errors = validate_platform_captions(
            platforms=[PlatformChoices.TWITTER],
            caption="A" * 281,
            brand=brand,
        )
        assert PlatformChoices.TWITTER in errors
        assert (
            "280 character limit for standard accounts"
            in errors[PlatformChoices.TWITTER]
        )

    def test_twitter_premium_account_allows_long_text(self, brand):
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.TWITTER,
            account_name="premium_tw",
            external_id="456",
            access_token="tok",
            token_expires_at=timezone.now() + timezone.timedelta(days=30),
            metadata={"is_premium": True},
        )
        errors = validate_platform_captions(
            platforms=[PlatformChoices.TWITTER],
            caption="A" * 1500,
            brand=brand,
        )
        assert errors == {}

    def test_twitter_premium_account_exceeds_25000(self, brand):
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.TWITTER,
            account_name="premium_tw",
            external_id="456",
            access_token="tok",
            token_expires_at=timezone.now() + timezone.timedelta(days=30),
            metadata={"is_premium": True},
        )
        errors = validate_platform_captions(
            platforms=[PlatformChoices.TWITTER],
            caption="A" * 25001,
            brand=brand,
        )
        assert PlatformChoices.TWITTER in errors
        assert (
            "25000 character limit for Premium accounts"
            in errors[PlatformChoices.TWITTER]
        )


class TestSerializersCaptionLimits:
    """Tests for DRF serializers enforcing platform limits."""

    def test_photo_serializer_threads_exceeds_500(self):
        data = {
            "photo_keys": ["photos/1.jpg"],
            "caption": "A" * 531,
            "platforms": [PlatformChoices.THREADS],
        }
        serializer = PhotoPostCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert PlatformChoices.THREADS in serializer.errors
        assert "500 characters" in str(serializer.errors[PlatformChoices.THREADS])

    def test_photo_serializer_threads_with_override_passes(self):
        data = {
            "photo_keys": ["photos/1.jpg"],
            "caption": "A" * 531,
            "platforms": [PlatformChoices.THREADS],
            "platform_settings": {"threads": {"caption": "Short caption under 500"}},
        }
        serializer = PhotoPostCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_video_serializer_threads_exceeds_500(self):
        data = {
            "video_key": "videos/1.mp4",
            "caption": "A" * 510,
            "platforms": [PlatformChoices.THREADS],
        }
        serializer = ContentPostCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert PlatformChoices.THREADS in serializer.errors

    def test_text_serializer_threads_exceeds_500(self):
        data = {
            "caption": "A" * 550,
            "platforms": [PlatformChoices.THREADS],
        }
        serializer = TextPostCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert PlatformChoices.THREADS in serializer.errors

    def test_update_serializer_threads_exceeds_500(self, user, brand):
        post = ContentPost.objects.create(
            user=user, brand=brand, caption="Initial", content_type="photo"
        )
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.THREADS,
            status=PostStatus.SCHEDULED,
        )

        data = {"caption": "A" * 520}
        serializer = ContentPostUpdateSerializer(instance=post, data=data)
        assert not serializer.is_valid()
        assert PlatformChoices.THREADS in serializer.errors


class TestContentPostServiceLimits:
    """Tests for ContentPostService enforcing caption limits."""

    def test_create_content_post_threads_exceeds_500_raises_value_error(
        self, db, user, brand, mocker
    ):
        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.THREADS,
            account_name="threads_user",
            external_id="threads_123",
            access_token="token",
            token_expires_at=expires,
        )

        with pytest.raises(ValueError) as exc:
            ContentPostService.create_content_post(
                user=user,
                media_keys=["photos/p.jpg"],
                caption="A" * 531,
                platforms=[PlatformChoices.THREADS],
                content_type="photo",
            )
        assert "Threads caption is limited to 500 characters" in str(exc.value)

    def test_update_content_post_threads_exceeds_500_raises_value_error(
        self, db, user, brand
    ):
        post = ContentPost.objects.create(
            user=user,
            brand=brand,
            caption="Short",
            content_type="photo",
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
        )
        ContentPostPlatform.objects.create(
            content_post=post,
            platform=PlatformChoices.THREADS,
            status=PostStatus.SCHEDULED,
            caption="Short",
        )

        with pytest.raises(ValueError) as exc:
            ContentPostService.update_content_post(
                content_post=post,
                validated_data={"caption": "B" * 520},
            )
        assert "Threads caption is limited to 500 characters" in str(exc.value)


class TestApiEndpointsValidation:
    """Integration test via API endpoint verifying HTTP 400 response."""

    def test_api_photo_threads_exceeds_500_returns_400(
        self, db, authenticated_client, user, brand
    ):
        expires = timezone.now() + timezone.timedelta(days=30)
        SocialAccount.objects.create(
            brand=brand,
            platform=PlatformChoices.THREADS,
            account_name="threads_user",
            external_id="threads_123",
            access_token="token",
            token_expires_at=expires,
        )

        response = authenticated_client.post(
            reverse("content-post-photo"),
            {
                "photo_keys": ["photos/sample.jpg"],
                "caption": "A" * 531,
                "platforms": [PlatformChoices.THREADS],
            },
            format="json",
        )

        assert response.status_code == 400
        assert PlatformChoices.THREADS in response.data
        assert "500 characters" in str(response.data[PlatformChoices.THREADS])
