import calendar
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from mcp_server.djangomcp import MCPToolset

from content.enums import TextPlatformOptions
from content.models import ContentPost
from content.selectors import ContentPostSelector
from content.serializers import ContentPostResponseSerializer
from content.services.content_post_service import ContentPostService
from mcp_integration.services import MCPContextService
from users.serializers import BrandBriefSerializer, ConnectedAccountSerializer
from users.services.brand_service import BrandService
from users.services.user_service import UserService

ALLOWED_TEXT_PLATFORMS = {choice[0] for choice in TextPlatformOptions.choices}


class PostGleeMCPToolset(MCPToolset):
    """MCP tools for managing PostGlee brands, connected social accounts, and posts."""

    def list_brands(self) -> list[dict[str, Any]]:
        """
        List all PostGlee brands accessible by the authenticated user.
        Returns each brand's id, name, logo_url, role, and whether it is the active brand.
        """
        user = MCPContextService.require_scope(self.request, "accounts:read")
        active_brand = UserService.get_active_brand(user)
        active_brand_id = active_brand.id if active_brand else None
        brands = BrandService.get_accessible_brands(user)
        return BrandBriefSerializer(
            brands,
            many=True,
            context={"active_brand_id": active_brand_id, "user": user},
        ).data

    def list_connected_accounts(
        self, brand_id: str | None = None
    ) -> dict[str, Any]:
        """
        List connected social media accounts for a brand (defaults to the user's active brand).

        :param brand_id: Optional UUID of the brand to inspect.
        """
        _user, brand = MCPContextService.resolve_brand(
            self.request, required_scope="accounts:read", brand_id=brand_id
        )
        accounts = sorted(
            brand.social_accounts.all(),
            key=lambda acc: acc.last_connected_at,
        )
        return {
            "brand_id": str(brand.id),
            "brand_name": brand.name,
            "connected_accounts": ConnectedAccountSerializer(
                accounts, many=True
            ).data,
        }

    def list_scheduled_posts(
        self,
        brand_id: str | None = None,
        platform: str | None = None,
        content_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        List upcoming scheduled posts for a brand (defaults to the user's active brand).

        :param brand_id: Optional UUID of the brand.
        :param platform: Optional platform filter (e.g. facebook, linkedin, twitter, threads, instagram, tiktok, youtube).
        :param content_type: Optional content type filter (text, photo, video).
        :param limit: Optional maximum number of posts to return.
        """
        _user, brand = MCPContextService.resolve_brand(
            self.request, required_scope="posts:read", brand_id=brand_id
        )
        posts = ContentPostSelector.get_scheduled_posts(
            brand=brand,
            platform=platform,
            content_type=content_type,
            limit=limit,
        )
        return ContentPostResponseSerializer(posts, many=True).data

    def get_calendar(
        self,
        brand_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve calendar posts for a brand within a date range (YYYY-MM-DD).
        Defaults to the current calendar month when dates are omitted.

        :param brand_id: Optional UUID of the brand.
        :param start_date: Optional start date in YYYY-MM-DD format.
        :param end_date: Optional end date in YYYY-MM-DD format.
        """
        _user, brand = MCPContextService.resolve_brand(
            self.request, required_scope="posts:read", brand_id=brand_id
        )

        parsed_start = parse_date(start_date) if start_date else None
        parsed_end = parse_date(end_date) if end_date else None

        if start_date and not parsed_start:
            raise ValueError("Invalid start_date format. Please use YYYY-MM-DD.")
        if end_date and not parsed_end:
            raise ValueError("Invalid end_date format. Please use YYYY-MM-DD.")

        today = timezone.now().date()
        if not parsed_start and not parsed_end:
            parsed_start = today.replace(day=1)
            _, last_day = calendar.monthrange(today.year, today.month)
            parsed_end = today.replace(day=last_day)
        elif not parsed_start and parsed_end:
            parsed_start = parsed_end.replace(day=1)
        elif parsed_start and not parsed_end:
            _, last_day = calendar.monthrange(parsed_start.year, parsed_start.month)
            parsed_end = parsed_start.replace(day=last_day)

        if parsed_start > parsed_end:
            raise ValueError("start_date cannot be after end_date.")

        posts = ContentPostSelector.get_calendar_posts(
            brand=brand,
            start_date=parsed_start,
            end_date=parsed_end,
        )
        return ContentPostResponseSerializer(posts, many=True).data

    def get_post(self, post_id: str) -> dict[str, Any]:
        """
        Get full details and per-platform publishing status of a post by ID.

        :param post_id: UUID of the ContentPost.
        """
        user = MCPContextService.require_scope(self.request, "posts:read")
        try:
            post = ContentPostSelector.get_content_post(post_id=post_id, user=user)
        except ContentPost.DoesNotExist as exc:
            raise ValueError("Content post not found.") from exc
        return ContentPostResponseSerializer(post).data

    def create_post(
        self,
        caption: str,
        platforms: list[str],
        scheduled_at: str | None = None,
        platform_settings: dict[str, Any] | None = None,
        brand_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create and publish (or schedule) a text post to one or more connected platforms.
        Supported text platforms: facebook, linkedin, threads, twitter.

        :param caption: The text body of the post.
        :param platforms: List of target platforms (e.g. ["linkedin", "twitter"]).
        :param scheduled_at: Optional ISO-8601 datetime string for scheduling in the future. If omitted, publishes immediately.
        :param platform_settings: Optional per-platform overrides, e.g. {"linkedin": {"caption": "..."}}.
        :param brand_id: Optional UUID of the target brand (defaults to the user's active brand).
        """
        user, brand = MCPContextService.resolve_brand(
            self.request, required_scope="posts:write", brand_id=brand_id
        )

        if not caption or not caption.strip():
            raise ValueError("caption cannot be empty.")
        if not platforms:
            raise ValueError("At least one target platform is required.")

        unsupported = [p for p in platforms if p not in ALLOWED_TEXT_PLATFORMS]
        if unsupported:
            raise ValueError(
                f"Unsupported platform(s) for text posts: {', '.join(unsupported)}. "
                f"Supported text platforms are: {', '.join(sorted(ALLOWED_TEXT_PLATFORMS))}."
            )

        parsed_scheduled_at = None
        if scheduled_at:
            parsed_scheduled_at = parse_datetime(scheduled_at)
            if not parsed_scheduled_at:
                raise ValueError(
                    "Invalid scheduled_at format. Use an ISO-8601 datetime (e.g. 2026-11-01T14:00:00Z)."
                )
            if timezone.is_naive(parsed_scheduled_at):
                parsed_scheduled_at = timezone.make_aware(parsed_scheduled_at)

        post = ContentPostService.create_content_post(
            user=user,
            brand=brand,
            media_keys=[],
            caption=caption,
            platforms=platforms,
            platform_settings=platform_settings or {},
            content_type="text",
            scheduled_at=parsed_scheduled_at,
        )
        return ContentPostResponseSerializer(post).data

    def update_post(
        self,
        post_id: str,
        caption: str | None = None,
        scheduled_at: str | None = None,
        platforms: list[str] | None = None,
        platform_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update a pending or scheduled post's caption, schedule time, platforms, or platform settings.

        :param post_id: UUID of the ContentPost to update.
        :param caption: Optional updated caption text.
        :param scheduled_at: Optional updated ISO-8601 scheduled datetime string.
        :param platforms: Optional updated list of target platforms.
        :param platform_settings: Optional updated per-platform settings dictionary.
        """
        user = MCPContextService.require_scope(self.request, "posts:write")
        try:
            content_post = ContentPostSelector.get_content_post(
                post_id=post_id, user=user
            )
        except ContentPost.DoesNotExist as exc:
            raise ValueError("Content post not found.") from exc

        validated_data: dict[str, Any] = {}
        if caption is not None:
            validated_data["caption"] = caption
        if scheduled_at is not None:
            if scheduled_at == "":
                validated_data["scheduled_at"] = None
            else:
                parsed_dt = parse_datetime(scheduled_at)
                if not parsed_dt:
                    raise ValueError(
                        "Invalid scheduled_at format. Use an ISO-8601 datetime."
                    )
                if timezone.is_naive(parsed_dt):
                    parsed_dt = timezone.make_aware(parsed_dt)
                validated_data["scheduled_at"] = parsed_dt
        if platforms is not None:
            if content_post.content_type == "text":
                unsupported = [
                    p for p in platforms if p not in ALLOWED_TEXT_PLATFORMS
                ]
                if unsupported:
                    raise ValueError(
                        f"Unsupported platform(s) for text posts: {', '.join(unsupported)}."
                    )
            validated_data["platforms"] = platforms
        if platform_settings is not None:
            validated_data["platform_settings"] = platform_settings

        updated = ContentPostService.update_content_post(
            content_post=content_post,
            validated_data=validated_data,
        )
        return ContentPostResponseSerializer(updated).data

    def delete_post(self, post_id: str) -> dict[str, Any]:
        """
        Delete a pending or scheduled post by ID.

        :param post_id: UUID of the ContentPost to delete.
        """
        user = MCPContextService.require_scope(self.request, "posts:write")
        try:
            content_post = ContentPostSelector.get_content_post(
                post_id=post_id, user=user
            )
        except ContentPost.DoesNotExist as exc:
            raise ValueError("Content post not found.") from exc

        ContentPostService.delete_content_post(content_post)
        return {"deleted": True, "post_id": str(post_id)}

