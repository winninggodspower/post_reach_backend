from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from social_accounts.models import SocialAccount
from social_accounts.services.social_account_connection_service import (
    SocialAccountConnectionService,
)
from utils.r2_storage import R2StorageService

pytestmark = pytest.mark.django_db


class TestSocialAccountConnectionServiceProfilePicture:
    """Tests for platform profile picture and brand logo syncing in SocialAccountConnectionService."""

    def test_sync_platform_profile_picture_returns_none_when_empty(self, brand):
        """Should immediately return None without calling HTTP or R2 if fetched_raw_url is empty."""
        result = SocialAccountConnectionService._sync_platform_profile_picture(
            brand=brand,
            platform="youtube",
            fetched_raw_url=None,
            external_id="channel_123",
        )
        assert result is None

    @patch("social_accounts.services.social_account_connection_service.httpx.Client")
    @patch.object(R2StorageService, "generate_key")
    @patch.object(R2StorageService, "upload_file")
    @patch.object(R2StorageService, "generate_presigned_url")
    @patch.object(R2StorageService, "delete_from_url")
    def test_sync_platform_profile_picture_uses_platform_profile_content_type_and_deletes_old(
        self,
        mock_delete,
        mock_presigned,
        mock_upload,
        mock_gen_key,
        mock_client_cls,
        brand,
    ):
        """Should use platform_profile content type and delete existing R2 URL."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = b"fake-image-bytes"
        mock_client.__enter__.return_value.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        mock_gen_key.return_value = "platform_profiles/2026-09-06/uuid.jpg"
        mock_presigned.return_value = (
            "https://r2.example.com/platform_profiles/2026-09-06/uuid.jpg"
        )

        old_url = "https://r2.example.com/platform_profiles/2026-09-06/old.jpg"

        synced_url = SocialAccountConnectionService._sync_platform_profile_picture(
            brand=brand,
            platform="youtube",
            fetched_raw_url="https://yt3.ggpht.com/avatar.jpg",
            external_id="yt_123",
            existing_r2_url=old_url,
        )

        mock_gen_key.assert_called_once_with(
            content_type="platform_profile", extension="jpg"
        )
        mock_upload.assert_called_once_with(
            b"fake-image-bytes",
            "platform_profiles/2026-09-06/uuid.jpg",
            content_type="platform_profile",
        )
        mock_delete.assert_called_once_with(old_url)
        assert (
            synced_url == "https://r2.example.com/platform_profiles/2026-09-06/uuid.jpg"
        )

    @patch.object(SocialAccountConnectionService, "_sync_platform_profile_picture")
    def test_save_account_sets_brand_logo_if_initially_none(self, mock_sync, brand):
        """Should set brand.logo_url fallback if brand has no logo."""
        brand.logo_url = None
        brand.save(update_fields=["logo_url"])

        now = timezone.now()
        expiry = now + timedelta(days=30)
        mock_sync.return_value = "https://r2.example.com/platform_profiles/new.jpg"

        account, _ = SocialAccountConnectionService._save_account(
            brand=brand,
            platform="youtube",
            defaults={
                "account_name": "My Channel",
                "external_id": "yt_123",
                "profile_picture_url": "https://yt3.ggpht.com/raw.jpg",
                "access_token": "token123",
                "token_expires_at": expiry,
            },
        )

        brand.refresh_from_db()
        assert brand.logo_url == "https://r2.example.com/platform_profiles/new.jpg"
        assert (
            account.profile_picture_url
            == "https://r2.example.com/platform_profiles/new.jpg"
        )

    @patch.object(SocialAccountConnectionService, "_sync_platform_profile_picture")
    def test_save_account_updates_brand_logo_if_it_matches_old_account_image(
        self, mock_sync, brand
    ):
        """Should update brand.logo_url if brand logo was pointing to the account's previous image."""
        now = timezone.now()
        expiry = now + timedelta(days=30)
        old_url = "https://r2.example.com/platform_profiles/old.jpg"
        new_url = "https://r2.example.com/platform_profiles/new.jpg"

        # Existing account and brand both point to old_url
        SocialAccount.objects.create(
            brand=brand,
            platform="youtube",
            account_name="My Channel",
            external_id="yt_123",
            profile_picture_url=old_url,
            access_token="token123",
            token_expires_at=expiry,
        )
        brand.logo_url = old_url
        brand.save(update_fields=["logo_url"])

        mock_sync.return_value = new_url

        SocialAccountConnectionService._save_account(
            brand=brand,
            platform="youtube",
            defaults={
                "account_name": "My Channel",
                "external_id": "yt_123",
                "profile_picture_url": "https://yt3.ggpht.com/new_raw.jpg",
                "access_token": "token123",
                "token_expires_at": expiry,
            },
        )

        brand.refresh_from_db()
        assert brand.logo_url == new_url

    @patch.object(SocialAccountConnectionService, "_sync_platform_profile_picture")
    def test_save_account_does_not_overwrite_custom_brand_logo(self, mock_sync, brand):
        """Should NOT update brand.logo_url if brand already has a custom logo different from old account image."""
        now = timezone.now()
        expiry = now + timedelta(days=30)
        custom_logo_url = "https://r2.example.com/brand_logos/custom_user_logo.png"
        old_account_url = "https://r2.example.com/platform_profiles/old_yt.jpg"
        new_account_url = "https://r2.example.com/platform_profiles/new_yt.jpg"

        SocialAccount.objects.create(
            brand=brand,
            platform="youtube",
            account_name="My Channel",
            external_id="yt_123",
            profile_picture_url=old_account_url,
            access_token="token123",
            token_expires_at=expiry,
        )
        brand.logo_url = custom_logo_url
        brand.save(update_fields=["logo_url"])

        mock_sync.return_value = new_account_url

        SocialAccountConnectionService._save_account(
            brand=brand,
            platform="youtube",
            defaults={
                "account_name": "My Channel",
                "external_id": "yt_123",
                "profile_picture_url": "https://yt3.ggpht.com/new_raw.jpg",
                "access_token": "token123",
                "token_expires_at": expiry,
            },
        )

        brand.refresh_from_db()
        assert brand.logo_url == custom_logo_url

    @patch.object(SocialAccountConnectionService, "_sync_platform_profile_picture")
    def test_save_account_sets_and_updates_last_connected_at(self, mock_sync, brand):
        """Initial connection and re-connection should set and update last_connected_at."""
        mock_sync.return_value = "https://r2.example.com/pic.jpg"
        past_time = timezone.now() - timedelta(days=7)

        # 1. First connection
        account, created = SocialAccountConnectionService._save_account(
            brand=brand,
            platform="youtube",
            defaults={
                "account_name": "My Channel",
                "external_id": "yt_123",
                "profile_picture_url": "https://yt3.ggpht.com/avatar.jpg",
                "access_token": "token123",
                "token_expires_at": timezone.now() + timedelta(days=30),
            },
        )
        assert created is True
        initial_connected_at = account.last_connected_at
        assert initial_connected_at is not None

        # Simulate time passing and backdate created_at & last_connected_at
        SocialAccount.objects.filter(id=account.id).update(
            last_connected_at=past_time,
        )
        account.refresh_from_db()
        assert account.last_connected_at == past_time

        # 2. Re-connection / re-authorization via _save_account
        reconnected_account, created = SocialAccountConnectionService._save_account(
            brand=brand,
            platform="youtube",
            defaults={
                "account_name": "My Channel",
                "external_id": "yt_123",
                "profile_picture_url": "https://yt3.ggpht.com/avatar.jpg",
                "access_token": "token456",
                "token_expires_at": timezone.now() + timedelta(days=60),
            },
        )
        assert created is False
        assert reconnected_account.last_connected_at > past_time

        # 3. Background token save updates updated_at, but NOT last_connected_at
        saved_last_connected = reconnected_account.last_connected_at
        reconnected_account.access_token = "token789"
        reconnected_account.save()
        reconnected_account.refresh_from_db()
        assert reconnected_account.last_connected_at == saved_last_connected

