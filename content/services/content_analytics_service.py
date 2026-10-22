from datetime import timedelta
from typing import Any

from django.db.models import Avg, Sum
from django.utils import timezone

from content.enums import PostStatus
from content.models import ContentPost, ContentPostPlatform, PostPlatformMetric
from integrations.providers.facebook_service import FacebookService
from integrations.providers.instagram_service import InstagramService
from integrations.providers.linkedin_service import LinkedinService
from integrations.providers.threads_service import ThreadsService
from integrations.providers.tiktok_service import TiktokService
from integrations.providers.twitter_service import TwitterService
from integrations.providers.youtube_service import YoutubeService
from social_accounts.enums import PlatformChoices
from social_accounts.models import SocialAccount
from users.models import Brand
from utils.custom_logger import CustomLogger, log_exceptions

SYNC_CACHE_TTL_MINUTES = 60

PROVIDER_MAP = {
    PlatformChoices.YOUTUBE: YoutubeService,
    PlatformChoices.INSTAGRAM: InstagramService,
    PlatformChoices.TIKTOK: TiktokService,
    PlatformChoices.FACEBOOK: FacebookService,
    PlatformChoices.LINKEDIN: LinkedinService,
    PlatformChoices.TWITTER: TwitterService,
    PlatformChoices.THREADS: ThreadsService,
}


class ContentAnalyticsService:
    """
    Lean service for fetching, calculating, and caching live engagement metrics
    for published content posts across social media platforms.
    """

    @classmethod
    @log_exceptions()
    def sync_platform_post_metric(
        cls, entry: ContentPostPlatform, force: bool = False
    ) -> PostPlatformMetric:
        """
        Retrieves or updates the PostPlatformMetric for a single platform post.
        Uses 1-hour in-place cache unless force=True.
        """
        metric, _ = PostPlatformMetric.objects.get_or_create(
            content_post_platform=entry,
        )

        # Only sync posts that have been posted and have a platform post ID
        if entry.status != PostStatus.POSTED or not entry.platform_post_id:
            return metric

        # Check if cache is still fresh
        if (
            not force
            and metric.last_synced_at is not None
            and metric.last_synced_at
            >= timezone.now() - timedelta(minutes=SYNC_CACHE_TTL_MINUTES)
        ):
            return metric

        # Resolve provider
        provider_cls = PROVIDER_MAP.get(entry.platform)
        if not provider_cls or not hasattr(provider_cls, "get_post_metrics"):
            return metric

        # Resolve connected social account
        brand = entry.content_post.brand
        social_account = SocialAccount.objects.filter(
            brand=brand, platform=entry.platform
        ).first()

        if not social_account:
            return metric

        access_token = social_account.get_access_token()
        if not access_token:
            return metric

        kwargs = {
            "platform_post_id": entry.platform_post_id,
            "access_token": access_token,
        }
        if entry.platform == PlatformChoices.TWITTER and getattr(
            social_account, "access_token_secret", None
        ):
            kwargs["access_token_secret"] = social_account.access_token_secret

        try:
            data = provider_cls.get_post_metrics(**kwargs)
        except Exception as exc:
            CustomLogger.warning(
                f"Failed to fetch live metrics for post {entry.id} on {entry.platform}: {exc}"
            )
            return metric

        if not data:
            return metric

        views = int(data.get("views", 0) or 0)
        reach = int(data.get("reach", 0) or 0)
        likes = int(data.get("likes", 0) or 0)
        comments = int(data.get("comments", 0) or 0)
        shares = int(data.get("shares", 0) or 0)
        saves = int(data.get("saves", 0) or 0)
        clicks = int(data.get("clicks", 0) or 0)

        # Engagement rate calculation
        if views > 0:
            engagement_rate = round(
                ((likes + comments + shares + saves) / views) * 100, 2
            )
        else:
            engagement_rate = 0.0

        metric.views = views
        metric.reach = reach
        metric.likes = likes
        metric.comments = comments
        metric.shares = shares
        metric.saves = saves
        metric.clicks = clicks
        metric.engagement_rate = engagement_rate
        metric.last_synced_at = timezone.now()
        metric.raw_data = data.get("raw", {})
        metric.save()

        return metric

    @classmethod
    @log_exceptions()
    def get_or_sync_post_analytics(
        cls, content_post: ContentPost, force_refresh: bool = False
    ) -> dict[str, Any]:
        """
        Returns consolidated live engagement analytics for a ContentPost across all target platforms.
        """
        platforms_data = []
        total_views = 0
        total_reach = 0
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_saves = 0
        total_clicks = 0

        entries = content_post.platform_entries.all()
        for entry in entries:
            metric = cls.sync_platform_post_metric(entry, force=force_refresh)

            total_views += metric.views
            total_reach += metric.reach
            total_likes += metric.likes
            total_comments += metric.comments
            total_shares += metric.shares
            total_saves += metric.saves
            total_clicks += metric.clicks

            platforms_data.append(
                {
                    "platform": entry.platform,
                    "status": entry.status,
                    "platform_post_id": entry.platform_post_id,
                    "post_url": entry.post_url,
                    "views": metric.views,
                    "reach": metric.reach,
                    "likes": metric.likes,
                    "comments": metric.comments,
                    "shares": metric.shares,
                    "saves": metric.saves,
                    "clicks": metric.clicks,
                    "engagement_rate": metric.engagement_rate,
                    "last_synced_at": metric.last_synced_at,
                }
            )

        if total_views > 0:
            overall_engagement_rate = round(
                (
                    (total_likes + total_comments + total_shares + total_saves)
                    / total_views
                )
                * 100,
                2,
            )
        else:
            overall_engagement_rate = 0.0

        return {
            "post_id": content_post.id,
            "brand_id": content_post.brand_id,
            "caption": content_post.caption,
            "content_type": content_post.content_type,
            "scheduled_at": content_post.scheduled_at,
            "created_at": content_post.created_at,
            "total_views": total_views,
            "total_reach": total_reach,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_saves": total_saves,
            "total_clicks": total_clicks,
            "overall_engagement_rate": overall_engagement_rate,
            "platforms": platforms_data,
        }

    @classmethod
    @log_exceptions()
    def get_brand_analytics(cls, brand: Brand, days: int = 30) -> dict[str, Any]:
        """
        Calculates brand-level content engagement KPIs and top performing posts over a given window.
        """
        since_date = timezone.now() - timedelta(days=days)

        posts_qs = ContentPost.objects.filter(brand=brand, created_at__gte=since_date)
        total_posts = posts_qs.count()

        # Aggregate metrics across all platform posts of this brand
        metrics_qs = PostPlatformMetric.objects.filter(
            content_post_platform__content_post__brand=brand,
            content_post_platform__content_post__created_at__gte=since_date,
        )

        aggregates = metrics_qs.aggregate(
            total_views=Sum("views"),
            total_reach=Sum("reach"),
            total_likes=Sum("likes"),
            total_comments=Sum("comments"),
            total_shares=Sum("shares"),
            total_saves=Sum("saves"),
            total_clicks=Sum("clicks"),
            avg_engagement_rate=Avg("engagement_rate"),
        )

        total_views = aggregates.get("total_views") or 0
        total_reach = aggregates.get("total_reach") or 0
        total_likes = aggregates.get("total_likes") or 0
        total_comments = aggregates.get("total_comments") or 0
        total_shares = aggregates.get("total_shares") or 0
        total_saves = aggregates.get("total_saves") or 0
        total_clicks = aggregates.get("total_clicks") or 0
        avg_rate = round(aggregates.get("avg_engagement_rate") or 0.0, 2)

        # Platform-by-platform breakdown
        platform_breakdown = {}
        for entry in metrics_qs.select_related("content_post_platform"):
            p = entry.content_post_platform.platform
            if p not in platform_breakdown:
                platform_breakdown[p] = {
                    "platform": p,
                    "views": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "posts_count": 0,
                }
            platform_breakdown[p]["views"] += entry.views
            platform_breakdown[p]["likes"] += entry.likes
            platform_breakdown[p]["comments"] += entry.comments
            platform_breakdown[p]["shares"] += entry.shares
            platform_breakdown[p]["posts_count"] += 1

        # Top 5 performing posts (ordered by views, then likes)
        top_platform_metrics = metrics_qs.select_related(
            "content_post_platform", "content_post_platform__content_post"
        ).order_by("-views", "-likes")[:5]

        top_posts = [
            {
                "post_id": m.content_post_platform.content_post_id,
                "platform": m.content_post_platform.platform,
                "caption": m.content_post_platform.content_post.caption,
                "post_url": m.content_post_platform.post_url,
                "views": m.views,
                "likes": m.likes,
                "comments": m.comments,
                "shares": m.shares,
                "engagement_rate": m.engagement_rate,
            }
            for m in top_platform_metrics
        ]

        return {
            "brand_id": brand.id,
            "brand_name": brand.name,
            "time_range_days": days,
            "total_posts": total_posts,
            "total_views": total_views,
            "total_reach": total_reach,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_saves": total_saves,
            "total_clicks": total_clicks,
            "average_engagement_rate": avg_rate,
            "platforms": list(platform_breakdown.values()),
            "top_posts": top_posts,
        }
