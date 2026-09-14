"""
Central namespace for all frontend URL and route generation across PostReach.

All frontend URL builders live here so there is a single source of truth,
avoiding hardcoded URL strings and making routes easy to update.
"""

from typing import Optional
from uuid import UUID

from django.conf import settings


class FrontendUrls:
    """Central namespace for all frontend URL and route generation."""

    @classmethod
    def base(cls) -> str:
        """Returns the configured frontend base URL without a trailing slash."""
        return getattr(settings, "FRONTEND_URL", "https://postglee.com").rstrip("/")

    @classmethod
    def dashboard(cls) -> str:
        """URL to the main dashboard."""
        return f"{cls.base()}/dashboard"

    @classmethod
    def post_detail(cls, post_id: str | UUID) -> str:
        """URL to the post details page."""
        return f"{cls.base()}/posts/{post_id}"

    @classmethod
    def retry_post(cls, post_id: str | UUID) -> str:
        """URL to edit and retry publishing a failed post."""
        return f"{cls.base()}/posts/{post_id}/retry"

    @classmethod
    def social_connections(cls) -> str:
        """URL to social account connection settings."""
        return f"{cls.base()}/settings/connections"

    @classmethod
    def login(cls) -> str:
        """URL to login page."""
        return f"{cls.base()}/login"

    @classmethod
    def password_reset(cls, token: str) -> str:
        """URL to password reset page with token."""
        return f"{cls.base()}/reset-password?token={token}"
