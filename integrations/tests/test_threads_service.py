import urllib.parse
from unittest.mock import MagicMock

import pytest
from django.conf import settings
from django.core.cache import cache

from integrations.providers.threads_service import ThreadsService
from utils.cache_keys import CacheKeys
from utils.http import APIError

pytestmark = pytest.mark.django_db


class TestThreadsServiceAuth:
    """Tests for ThreadsService authentication methods."""

    def test_generate_auth_url_returns_url_with_required_params(self, user):
        """Should return a Threads OAuth URL with correct query parameters."""
        auth_url = ThreadsService.generate_auth_url(user_id=user.id)

        assert auth_url.startswith("https://threads.net/oauth/authorize?")
        assert "client_id=" in auth_url
        assert "redirect_uri=" in auth_url
        assert "state=" in auth_url
        assert "scope=" in auth_url
        assert "response_type=code" in auth_url

    def test_generate_auth_url_stores_state_in_cache(self, user):
        """Should store OAuth state in cache for CSRF protection."""
        auth_url = ThreadsService.generate_auth_url(user_id=user.id)

        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)
        state_from_url = params["state"][0]

        cached_state = cache.get(CacheKeys.threads_oauth_state(user.id))
        assert cached_state == state_from_url

    def test_exchange_code_for_token_success(self, mocker):
        """Should exchange auth code for short-lived then long-lived token."""
        mocker.patch.object(
            ThreadsService,
            "_get_short_lived_token",
            return_value={"access_token": "short_token_123", "user_id": "98765"},
        )
        mocker.patch.object(
            ThreadsService,
            "_get_long_lived_token",
            return_value={"access_token": "long_token_456", "expires_in": 5184000},
        )

        tokens, missing_scopes = ThreadsService.exchange_code_for_token(
            auth_code="code_abc", redirect_uri="https://example.com/callback"
        )

        assert tokens["access_token"] == "long_token_456"
        assert tokens["expires_in"] == 5184000
        assert tokens["user_id"] == "98765"
        assert missing_scopes == []

    def test_refresh_access_token_success(self, mocker):
        """Should refresh long-lived token via th_refresh_token."""
        mocker.patch.object(
            ThreadsService,
            "get",
            return_value={"access_token": "refreshed_token_789", "expires_in": 5184000},
        )

        result = ThreadsService.refresh_access_token("existing_token")
        assert result["access_token"] == "refreshed_token_789"
        assert result["expires_in"] == 5184000
        assert result["refresh_token"] is None

    def test_fetch_user_info_success(self, mocker):
        """Should fetch profile info and return username and ID."""
        mock_response = {
            "id": "123456789",
            "username": "threads_tester",
            "threads_profile_picture_url": "https://example.com/pic.jpg",
        }
        mocker.patch.object(ThreadsService, "get", return_value=mock_response)

        info = ThreadsService.fetch_user_info("valid_token")

        assert info["account_name"] == "threads_tester"
        assert info["external_id"] == "123456789"
        assert info["profile_picture_url"] == "https://example.com/pic.jpg"

    def test_fetch_user_info_failure(self, mocker):
        """Should raise ValueError if API call fails."""
        mocker.patch.object(ThreadsService, "get", side_effect=APIError("API error"))

        with pytest.raises(ValueError, match="Failed to fetch Threads user info"):
            ThreadsService.fetch_user_info("bad_token")

    def test_get_publishing_limit_success(self, mocker):
        """Should fetch current rate limit usage."""
        mock_response = {
            "data": [
                {
                    "quota_usage": 4,
                    "config": {"quota_total": 250, "quota_duration": 86400},
                }
            ]
        }
        mocker.patch.object(ThreadsService, "get", return_value=mock_response)

        limit_info = ThreadsService.get_publishing_limit(
            access_token="valid_token", threads_user_id="123456789"
        )
        assert limit_info["data"][0]["quota_usage"] == 4


class TestThreadsServicePublishing:
    """Tests for ThreadsService media and post publishing methods."""

    def test_publish_text_success(self, mocker):
        """Should create a TEXT container and publish it."""
        mock_post = mocker.patch.object(ThreadsService, "post")
        mock_post.side_effect = [
            {"id": "text_container_123"},
            {"id": "threads_post_999"},
        ]

        result = ThreadsService.publish_text(
            access_token="valid_token",
            threads_user_id="123456789",
            text="Hello Threads!",
        )

        assert result == {
            "platform_post_id": "threads_post_999",
            "status": "published",
        }
        assert mock_post.call_count == 2
        mock_post.assert_any_call(
            "/v1.0/123456789/threads",
            data={
                "media_type": "TEXT",
                "text": "Hello Threads!",
                "access_token": "valid_token",
            },
        )

    def test_publish_text_exceeds_character_limit(self):
        """Should raise ValueError if text exceeds 500 characters."""
        long_text = "x" * 501
        with pytest.raises(ValueError, match="limited to 500 characters"):
            ThreadsService.publish_text(
                access_token="token",
                threads_user_id="123456789",
                text=long_text,
            )

    def test_publish_photo_single_success(self, mocker):
        """Should create an IMAGE container and return processing status."""
        mock_post = mocker.patch.object(
            ThreadsService, "post", return_value={"id": "image_container_123"}
        )

        result = ThreadsService.publish_photo(
            access_token="valid_token",
            threads_user_id="123456789",
            photo_urls=["https://example.com/photo.jpg"],
            text="Post with photo",
        )

        assert result == {
            "platform_post_id": "image_container_123",
            "status": "processing",
        }
        mock_post.assert_called_once_with(
            "/v1.0/123456789/threads",
            data={
                "media_type": "IMAGE",
                "image_url": "https://example.com/photo.jpg",
                "text": "Post with photo",
                "access_token": "valid_token",
            },
        )

    def test_publish_photo_carousel_success(self, mocker):
        """Should create child IMAGE containers and parent CAROUSEL container."""
        mock_post = mocker.patch.object(ThreadsService, "post")
        mock_post.side_effect = [
            {"id": "child_1"},
            {"id": "child_2"},
            {"id": "carousel_container_999"},
        ]

        result = ThreadsService.publish_photo(
            access_token="valid_token",
            threads_user_id="123456789",
            photo_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
            text="Carousel caption",
        )

        assert result == {
            "platform_post_id": "carousel_container_999",
            "status": "processing",
        }
        assert mock_post.call_count == 3
        mock_post.assert_any_call(
            "/v1.0/123456789/threads",
            data={
                "media_type": "CAROUSEL",
                "children": "child_1,child_2",
                "text": "Carousel caption",
                "access_token": "valid_token",
            },
        )

    def test_publish_photo_carousel_exceeds_max_children(self):
        """Should raise ValueError if photo_urls exceeds 20 items."""
        urls = [f"https://example.com/{i}.jpg" for i in range(21)]
        with pytest.raises(ValueError, match="maximum of 20 children"):
            ThreadsService.publish_photo(
                access_token="token",
                threads_user_id="123456789",
                photo_urls=urls,
            )

    def test_publish_video_success(self, mocker):
        """Should create a VIDEO container and return processing status."""
        mock_post = mocker.patch.object(
            ThreadsService, "post", return_value={"id": "video_container_123"}
        )

        result = ThreadsService.publish_video(
            access_token="valid_token",
            threads_user_id="123456789",
            video_url="https://example.com/video.mp4",
            text="Check out this video!",
        )

        assert result == {
            "platform_post_id": "video_container_123",
            "status": "processing",
        }
        mock_post.assert_called_once_with(
            "/v1.0/123456789/threads",
            data={
                "media_type": "VIDEO",
                "video_url": "https://example.com/video.mp4",
                "text": "Check out this video!",
                "access_token": "valid_token",
            },
        )

    def test_check_container_status_finished(self, mocker):
        """Should return status when querying container status."""
        mocker.patch.object(ThreadsService, "get", return_value={"status": "FINISHED"})

        status = ThreadsService.check_container_status("token", "container_123")
        assert status == "FINISHED"

    def test_check_container_status_error(self, mocker):
        """Should raise ValueError if container processing failed."""
        mocker.patch.object(
            ThreadsService,
            "get",
            return_value={"status": "ERROR", "error_message": "Media decode error"},
        )

        with pytest.raises(
            ValueError, match="Threads container processing failed: Media decode error"
        ):
            ThreadsService.check_container_status("token", "container_123")

    def test_publish_container_success(self, mocker):
        """Should publish container and return platform_post_id."""
        mock_post = mocker.patch.object(
            ThreadsService, "post", return_value={"id": "published_media_123"}
        )

        result = ThreadsService.publish_container(
            access_token="token",
            threads_user_id="123456789",
            container_id="container_123",
        )
        assert result == {
            "platform_post_id": "published_media_123",
            "status": "published",
        }
        mock_post.assert_called_once_with(
            "/v1.0/123456789/threads_publish",
            data={
                "creation_id": "container_123",
                "access_token": "token",
            },
        )

    def test_get_permalink_success(self, mocker):
        """Should return permalink for published post."""
        mocker.patch.object(
            ThreadsService,
            "get",
            return_value={"permalink": "https://www.threads.net/@user/post/123"},
        )

        permalink = ThreadsService.get_permalink("token", "media_123")
        assert permalink == "https://www.threads.net/@user/post/123"
