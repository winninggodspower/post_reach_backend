from collections.abc import Iterable
from typing import Any

from social_accounts.enums import PlatformChoices
from users.models import Brand


def validate_platform_captions(
    *,
    platforms: Iterable[str],
    caption: str = "",
    platform_settings: dict[str, Any] | None = None,
    brand: Brand | None = None,
) -> dict[str, str]:
    """
    Validates caption lengths for each selected platform against platform limits.

    Rules:
    - Threads: max 500 characters.
    - Twitter / X: max 280 characters for standard accounts, up to 25,000 characters for X Premium / Pro.
    - Instagram: max 2,200 characters.
    - LinkedIn: max 3,000 characters.
    - TikTok: max 2,200 characters.

    Returns:
        dict[str, str]: Map of platform name to validation error message. Empty if all valid.
    """
    errors: dict[str, str] = {}
    platform_settings = platform_settings or {}
    caption = caption or ""

    for platform in platforms:
        plat_settings = platform_settings.get(platform, {})
        if not isinstance(plat_settings, dict):
            plat_settings = {}

        # Resolve the effective caption for this platform
        if platform == PlatformChoices.YOUTUBE:
            plat_caption = plat_settings.get(
                "description", plat_settings.get("caption", caption)
            )
        else:
            plat_caption = plat_settings.get("caption", caption)

        if not plat_caption:
            continue

        text_len = len(plat_caption)

        if platform == PlatformChoices.THREADS:
            if text_len > 500:
                errors[platform] = (
                    f"Threads caption is limited to 500 characters. Current length: {text_len}."
                )

        elif platform == PlatformChoices.TWITTER:
            is_premium = False
            if brand:
                twitter_account = brand.social_accounts.filter(
                    platform=PlatformChoices.TWITTER
                ).first()
                if twitter_account and isinstance(twitter_account.metadata, dict):
                    is_premium = twitter_account.metadata.get("is_premium", False)

            limit = 25000 if is_premium else 280
            if text_len > limit:
                account_type = "Premium" if is_premium else "standard"
                errors[platform] = (
                    f"Twitter post exceeds the {limit} character limit for {account_type} accounts. "
                    f"Current length: {text_len}."
                )

        elif platform == PlatformChoices.INSTAGRAM:
            if text_len > 2200:
                errors[platform] = (
                    f"Instagram caption is limited to 2,200 characters. Current length: {text_len}."
                )

        elif platform == PlatformChoices.LINKEDIN:
            if text_len > 3000:
                errors[platform] = (
                    f"LinkedIn post is limited to 3,000 characters. Current length: {text_len}."
                )

        elif platform == PlatformChoices.TIKTOK:
            if text_len > 2200:
                errors[platform] = (
                    f"TikTok caption is limited to 2,200 characters. Current length: {text_len}."
                )

    return errors
