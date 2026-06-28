import pytest
from unittest.mock import MagicMock
from django.core.cache import cache
from django.conf import settings

from integrations.providers.instagram_service import InstagramService
from utils.cache_keys import CacheKeys
from utils.http import APIError

pytestmark = pytest.mark.django_db


class TestInstagramServiceAuth:
    """Tests for InstagramService authentication methods."""

    def test_generate_auth_url_returns_url_with_required_params(self, user):
        """Should return an Instagram OAuth URL with correct query parameters."""
        auth_url = InstagramService.generate_auth_url(user_id=user.id)

        assert auth_url.startswith("https://api.instagram.com/oauth/authorize?")
        assert "client_id=" in auth_url
        assert "redirect_uri=" in auth_url
        assert "state=" in auth_url
        assert "scope=" in auth_url
        assert "response_type=code" in auth_url

    def test_generate_auth_url_stores_state_in_cache(self, user):
        """Should store OAuth state in cache for CSRF protection."""
        auth_url = InstagramService.generate_auth_url(user_id=user.id)

        import urllib.parse
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)
        state_from_url = params["state"][0]

        cached_state = cache.get(CacheKeys.instagram_oauth_state(user.id))
        assert cached_state == state_from_url

    def test_fetch_user_info_success(self, mocker):
        """Should fetch profile info and return username and ID."""
        mock_response = {
            "id": "17841400797787220",
            "username": "instagram_user_test",
        }
        mocker.patch.object(InstagramService, "get", return_value=mock_response)

        info = InstagramService.fetch_user_info("test_access_token")

        assert info["account_name"] == "instagram_user_test"
        assert info["external_id"] == "17841400797787220"

    def test_fetch_user_info_failure(self, mocker):
        """Should raise ValueError if API call fails."""
        mocker.patch.object(
            InstagramService, "get", side_effect=APIError("Request failed")
        )

        with pytest.raises(ValueError, match="Failed to fetch Instagram user info"):
            InstagramService.fetch_user_info("bad_token")


class TestInstagramServicePublishing:
    """Tests for InstagramService media publishing methods."""

    def test_publish_video_success(self, mocker):
        """Should create a REELS container and publish it successfully."""
        mock_post = mocker.patch.object(InstagramService, "post")
        mock_get = mocker.patch.object(InstagramService, "get", return_value={"status_code": "FINISHED"})
        # Step 1 response: container creation
        # Step 2 response: publication
        mock_post.side_effect = [
            {"id": "container_reel_123"},
            {"id": "media_post_456"},
        ]

        result = InstagramService.publish_video(
            access_token="valid_token",
            instagram_account_id="17841400797787220",
            video_url="https://example.com/video.mp4",
            caption="Amazing Reel!",
        )

        assert result["platform_post_id"] == "media_post_456"
        assert mock_post.call_count == 2

        # Verify Step 1 parameters - must use REELS media_type!
        mock_post.assert_any_call(
            "/17841400797787220/media",
            data={
                "media_type": "REELS",
                "video_url": "https://example.com/video.mp4",
                "caption": "Amazing Reel!",
                "access_token": "valid_token",
            },
        )

        # Verify Step 2 parameters
        mock_post.assert_any_call(
            "/17841400797787220/media_publish",
            data={
                "creation_id": "container_reel_123",
                "access_token": "valid_token",
            },
        )

        # Verify status check call parameters
        mock_get.assert_called_once_with(
            "/container_reel_123",
            params={
                "fields": "status_code",
                "access_token": "valid_token",
            },
        )

    def test_publish_photo_single_success(self, mocker):
        """Should create an IMAGE container and publish it."""
        mock_post = mocker.patch.object(InstagramService, "post")
        mock_post.side_effect = [
            {"id": "container_photo_123"},
            {"id": "media_post_789"},
        ]

        result = InstagramService.publish_photo(
            access_token="valid_token",
            instagram_account_id="17841400797787220",
            photo_urls=["https://example.com/photo.jpg"],
            caption="Beautiful view!",
        )

        assert result["platform_post_id"] == "media_post_789"
        assert mock_post.call_count == 2

        mock_post.assert_any_call(
            "/17841400797787220/media",
            data={
                "media_type": "IMAGE",
                "image_url": "https://example.com/photo.jpg",
                "caption": "Beautiful view!",
                "access_token": "valid_token",
            },
        )

    def test_publish_photo_carousel_success(self, mocker):
        """Should create child IMAGE containers, a CAROUSEL container, and publish it."""
        mock_post = mocker.patch.object(InstagramService, "post")
        mock_post.side_effect = [
            {"id": "child_1"},
            {"id": "child_2"},
            {"id": "carousel_parent_999"},
            {"id": "published_media_111"},
        ]

        result = InstagramService.publish_photo(
            access_token="valid_token",
            instagram_account_id="17841400797787220",
            photo_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
            caption="Album post",
        )

        assert result["platform_post_id"] == "published_media_111"
        assert mock_post.call_count == 4

        # Check child container creations
        mock_post.assert_any_call(
            "/17841400797787220/media",
            data={
                "media_type": "IMAGE",
                "image_url": "https://example.com/1.jpg",
                "is_carousel_item": "true",
                "access_token": "valid_token",
            },
        )

        # Check carousel parent container creation
        mock_post.assert_any_call(
            "/17841400797787220/media",
            data={
                "media_type": "CAROUSEL",
                "children": "child_1,child_2",
                "caption": "Album post",
                "access_token": "valid_token",
            },
        )
