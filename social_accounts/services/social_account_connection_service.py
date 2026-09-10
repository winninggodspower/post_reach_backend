from datetime import timedelta

import httpx
from django.core.cache import cache
from django.utils import timezone

from integrations.providers.base import SocialAccountService
from integrations.providers.facebook_service import FacebookService
from integrations.providers.instagram_service import InstagramService
from integrations.providers.linkedin_service import LinkedinService
from integrations.providers.tiktok_service import TiktokService
from integrations.providers.youtube_service import YoutubeService
from social_accounts.models import SocialAccount
from utils.cache_keys import CacheKeys
from utils.custom_logger import CustomLogger, log_exceptions
from utils.r2_storage import R2StorageService


class SocialAccountConnectionService:
    @classmethod
    @log_exceptions()
    def _save_account(cls, *, brand, platform, defaults):
        # Look up any existing social account connection so we know its previous R2 profile picture URL
        existing_account = SocialAccount.objects.filter(
            brand=brand, platform=platform
        ).first()
        existing_r2_url = (
            existing_account.profile_picture_url if existing_account else None
        )

        # Upload the fetched platform profile picture to R2 in the dedicated platform_profiles folder and delete the old one
        synced_r2_url = cls._sync_platform_profile_picture(
            brand=brand,
            platform=platform,
            fetched_raw_url=defaults.get("profile_picture_url"),
            external_id=defaults.get("external_id", "unknown"),
            existing_r2_url=existing_r2_url,
        )
        defaults["profile_picture_url"] = synced_r2_url
        if "metadata" in defaults and "picture_url" in defaults["metadata"]:
            defaults["metadata"]["picture_url"] = synced_r2_url

        # Sync brand logo fallback:
        # 1. If brand has no logo yet, adopt this connected platform's synced picture.
        # 2. If brand's logo was set to this platform's previous image (which was just replaced/deleted from R2),
        #    update it to the new image so the brand logo doesn't become a broken link.
        # 3. If the brand has an official custom logo (brand.logo_url != existing_r2_url), preserve it untouched.
        if synced_r2_url and (not brand.logo_url or brand.logo_url == existing_r2_url):
            brand.logo_url = synced_r2_url
            brand.save(update_fields=["logo_url"])

        defaults["last_connected_at"] = timezone.now()

        return SocialAccount.objects.update_or_create(
            brand=brand,
            platform=platform,
            defaults=defaults,
        )

    @classmethod
    def _sync_platform_profile_picture(
        cls,
        brand,
        platform,
        fetched_raw_url,
        external_id,
        existing_r2_url=None,
    ):
        # If the platform returned no profile picture URL, nothing to sync
        if not fetched_raw_url:
            return None

        # Resolve existing R2 URL if not provided by caller
        if existing_r2_url is None:
            existing_account = SocialAccount.objects.filter(
                brand=brand, platform=platform
            ).first()
            existing_r2_url = (
                existing_account.profile_picture_url if existing_account else None
            )

        # Skip if the raw URL is somehow already the stored R2 URL
        if existing_r2_url == fetched_raw_url:
            return fetched_raw_url

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(fetched_raw_url)
                resp.raise_for_status()

                # Store social platform profile pictures in the dedicated 'platform_profiles' folder in R2
                key = R2StorageService.generate_key(
                    content_type="platform_profile", extension="jpg"
                )
                R2StorageService.upload_file(
                    resp.content, key, content_type="platform_profile"
                )
                synced_r2_url = R2StorageService.generate_presigned_url(key)

                if not synced_r2_url:
                    raise ValueError("Failed to generate presigned URL")

                # Delete the previous R2 image ONLY after successfully uploading the new one
                if existing_r2_url:
                    R2StorageService.delete_from_url(existing_r2_url)

                return synced_r2_url
        except Exception as e:
            CustomLogger.warning(
                "Failed to sync platform profile picture to R2",
                extra={
                    "identifier": external_id,
                    "url": fetched_raw_url,
                    "error": str(e),
                },
            )
            return fetched_raw_url

    @classmethod
    def _base_metadata(cls, platform, **extra):
        metadata = {"provider": platform}
        metadata.update(
            {key: value for key, value in extra.items() if value is not None}
        )
        return metadata

    @classmethod
    @log_exceptions()
    def connect_youtube(cls, *, user, brand, auth_code):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        credentials, missing_scopes = YoutubeService.exchange_code_for_token(
            auth_code=auth_code,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        # Fetch channel info (account name and external ID)
        channel_info = YoutubeService._fetch_channel_info(credentials)

        return cls._save_account(
            brand=resolved_brand,
            platform="youtube",
            defaults={
                "account_name": channel_info["account_name"],
                "external_id": channel_info["external_id"],
                "profile_picture_url": channel_info.get("profile_picture_url"),
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expires_at": credentials.expiry,
                "scope": " ".join(credentials.scopes),
                "metadata": cls._base_metadata(
                    "youtube",
                    profile_picture_url=channel_info.get("profile_picture_url"),
                ),
            },
        )

    @classmethod
    @log_exceptions()
    def connect_facebook(cls, *, user, brand, code, redirect_uri, page_id=""):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        cache_key = CacheKeys.facebook_access_token(code)
        cached_data = cache.get(cache_key)

        if cached_data:
            long_lived_token, expires_in = cached_data
            cache.delete(cache_key)
        else:
            long_lived_token, expires_in = FacebookService.exchange_code_for_token(
                code, redirect_uri
            )

        # Fetch Facebook pages and select the target page
        pages = FacebookService.get_facebook_pages(long_lived_token)
        if page_id:
            page = next((p for p in pages if p["id"] == page_id), None)
            if not page:
                raise ValueError(
                    f"Facebook page with ID '{page_id}' not found in your account"
                )
        else:
            page = pages[0]  # Default to the first page

        return cls._save_account(
            brand=resolved_brand,
            platform="facebook",
            defaults={
                "account_name": page["name"],
                "external_id": page["id"],
                "profile_picture_url": page.get("picture_url"),
                "access_token": page["access_token"],
                "token_expires_at": timezone.now() + timedelta(seconds=expires_in),
                "metadata": cls._base_metadata(
                    "facebook",
                    page_name=page["name"],
                    picture_url=page.get("picture_url"),
                ),
            },
        )

    @classmethod
    def connect_instagram(cls, *, user, brand, auth_code, redirect_uri):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        credentials, missing_scopes = InstagramService.exchange_code_for_token(
            auth_code=auth_code,
            redirect_uri=redirect_uri,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        # Fetch Instagram user info for username and ID
        user_info = InstagramService.fetch_user_info(credentials["access_token"])

        return cls._save_account(
            brand=resolved_brand,
            platform="instagram",
            defaults={
                "account_name": user_info["account_name"],
                "external_id": user_info["external_id"],
                "profile_picture_url": user_info.get("profile_picture_url"),
                "access_token": credentials["access_token"],
                "token_expires_at": timezone.now()
                + timedelta(seconds=credentials["expires_in"]),
                "metadata": cls._base_metadata(
                    "instagram",
                    account_name=user_info["account_name"],
                    profile_picture_url=user_info.get("profile_picture_url"),
                ),
            },
        )

    @classmethod
    @log_exceptions()
    def connect_tiktok(cls, *, user, brand, code, redirect_uri):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        token_data = TiktokService.exchange_code_for_token(code, user.id)

        access_token = token_data["access_token"]

        # Fetch TikTok user info (account name and external ID)
        user_info = TiktokService.fetch_user_info(access_token)

        return cls._save_account(
            brand=resolved_brand,
            platform="tiktok",
            defaults={
                "account_name": user_info["account_name"],
                "external_id": user_info["external_id"],
                "profile_picture_url": user_info.get("profile_picture_url"),
                "access_token": access_token,
                "refresh_token": token_data.get("refresh_token"),
                "token_expires_at": timezone.now()
                + timedelta(seconds=token_data["expires_in"]),
                "scope": token_data.get("scope", ""),
                "metadata": cls._base_metadata(
                    "tiktok",
                    account_name=user_info["account_name"],
                    profile_picture_url=user_info.get("profile_picture_url"),
                ),
            },
        )

    @classmethod
    @log_exceptions()
    def connect_linkedin(cls, *, user, brand, code, redirect_uri):
        resolved_brand = SocialAccountService._resolve_brand(user, brand)

        token_data = LinkedinService.exchange_code_for_token(code, redirect_uri)

        access_token = token_data["access_token"]

        # Fetch LinkedIn user info (account name and external ID)
        user_info = LinkedinService.fetch_user_info(access_token)

        return cls._save_account(
            brand=resolved_brand,
            platform="linkedin",
            defaults={
                "account_name": user_info["account_name"],
                "external_id": user_info["external_id"],
                "profile_picture_url": user_info.get("profile_picture_url"),
                "access_token": access_token,
                "refresh_token": token_data.get("refresh_token"),
                "token_expires_at": timezone.now()
                + timedelta(seconds=token_data["expires_in"]),
                "scope": token_data.get("scope", ""),
                "metadata": cls._base_metadata(
                    "linkedin",
                    account_name=user_info["account_name"],
                    profile_picture_url=user_info.get("profile_picture_url"),
                ),
            },
        )
