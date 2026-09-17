from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from content.enums import PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform, PendingUpload
from social_accounts.models import Brand, SocialAccount
from users.models import User
from utils.custom_logger import log_exceptions


class AdminAnalyticsService:
    """
    Stateless domain service for platform-wide analytics and admin telemetry.
    Aggregates high-level metrics across users, onboarding, brands,
    social accounts, posts, and media storage.
    """

    @classmethod
    def _get_completed_onboarding_count(cls) -> int:
        active_brand_completed = (
            Q(active_brand__isnull=False)
            & Q(active_brand__industry__isnull=False)
            & ~Q(active_brand__industry="")
            & Q(active_brand__posting_frequency__isnull=False)
            & ~Q(active_brand__posting_frequency="")
            & Q(active_brand__primary_platform__isnull=False)
            & ~Q(active_brand__primary_platform="")
            & Q(active_brand__team_size__isnull=False)
            & ~Q(active_brand__team_size="")
        )
        default_brand_completed = (
            Q(active_brand__isnull=True)
            & Q(brands__is_default=True)
            & Q(brands__industry__isnull=False)
            & ~Q(brands__industry="")
            & Q(brands__posting_frequency__isnull=False)
            & ~Q(brands__posting_frequency="")
            & Q(brands__primary_platform__isnull=False)
            & ~Q(brands__primary_platform="")
            & Q(brands__team_size__isnull=False)
            & ~Q(brands__team_size="")
        )

        completed_onboarding_filter = (
            Q(role__isnull=False)
            & ~Q(role="")
            & (active_brand_completed | default_brand_completed)
        )
        return User.objects.filter(completed_onboarding_filter).distinct().count()

    @classmethod
    @log_exceptions()
    def get_executive_summary(cls) -> dict:
        total_users = User.objects.count()
        completed_onboarding = cls._get_completed_onboarding_count()
        completion_rate = (
            round((completed_onboarding / total_users) * 100, 2)
            if total_users > 0
            else 0.0
        )
        total_connected_accounts = SocialAccount.objects.count()
        total_posts = ContentPost.objects.count()
        live_posts_count = (
            ContentPost.objects.filter(platform_entries__status=PostStatus.POSTED)
            .distinct()
            .count()
        )
        failed_posts_count = ContentPostPlatform.objects.filter(
            status=PostStatus.FAILED
        ).count()

        return {
            "total_users": total_users,
            "completed_onboarding": completed_onboarding,
            "onboarding_completion_rate_percentage": completion_rate,
            "total_connected_accounts": total_connected_accounts,
            "live_posts_count": live_posts_count,
            "total_posts": total_posts,
            "failed_posts_count": failed_posts_count,
        }

    @classmethod
    @log_exceptions()
    def get_platform_overview(cls) -> dict:
        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        summary_data = cls.get_executive_summary()
        users_data = cls._get_users_metrics(
            start_of_today=start_of_today,
            seven_days_ago=seven_days_ago,
            thirty_days_ago=thirty_days_ago,
        )
        brands_data = cls._get_brands_metrics()
        social_accounts_data = cls._get_social_accounts_metrics()
        posts_data = cls._get_posts_metrics(
            start_of_today=start_of_today,
            seven_days_ago=seven_days_ago,
            thirty_days_ago=thirty_days_ago,
        )
        storage_data = cls._get_storage_metrics()

        return {
            "summary": summary_data,
            "users": users_data,
            "brands": brands_data,
            "social_accounts": social_accounts_data,
            "posts": posts_data,
            "storage": storage_data,
        }

    @classmethod
    def _get_users_metrics(
        cls, *, start_of_today, seven_days_ago, thirty_days_ago
    ) -> dict:
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        completed_onboarding = cls._get_completed_onboarding_count()
        pending_onboarding = max(0, total_users - completed_onboarding)
        completion_rate = (
            round((completed_onboarding / total_users) * 100, 2)
            if total_users > 0
            else 0.0
        )

        # Role breakdown
        role_counts_query = dict(
            User.objects.values("role")
            .annotate(count=Count("id"))
            .values_list("role", "count")
        )

        roles_breakdown = {}
        unassigned_count = 0
        for raw_role, count in role_counts_query.items():
            if raw_role in [choice.value for choice in User.RoleChoices]:
                roles_breakdown[raw_role] = count
            else:
                unassigned_count += count

        for choice in User.RoleChoices:
            if choice.value not in roles_breakdown:
                roles_breakdown[choice.value] = 0
        roles_breakdown["unassigned"] = unassigned_count

        # Growth metrics
        joined_today = User.objects.filter(date_joined__gte=start_of_today).count()
        joined_this_week = User.objects.filter(date_joined__gte=seven_days_ago).count()
        joined_this_month = User.objects.filter(
            date_joined__gte=thirty_days_ago
        ).count()

        return {
            "total_users": total_users,
            "active_users": active_users,
            "completed_onboarding": completed_onboarding,
            "pending_onboarding": pending_onboarding,
            "onboarding_completion_rate_percentage": completion_rate,
            "roles_breakdown": roles_breakdown,
            "growth": {
                "joined_today": joined_today,
                "joined_this_week": joined_this_week,
                "joined_this_month": joined_this_month,
            },
        }

    @classmethod
    def _get_brands_metrics(cls) -> dict:
        total_brands = Brand.objects.count()
        brands_with_connected_accounts = (
            Brand.objects.filter(social_accounts__isnull=False).distinct().count()
        )

        industries_breakdown = dict(
            Brand.objects.exclude(industry__isnull=True)
            .exclude(industry="")
            .values("industry")
            .annotate(count=Count("id"))
            .values_list("industry", "count")
        )

        team_sizes_breakdown = dict(
            Brand.objects.exclude(team_size__isnull=True)
            .exclude(team_size="")
            .values("team_size")
            .annotate(count=Count("id"))
            .values_list("team_size", "count")
        )

        return {
            "total_brands": total_brands,
            "brands_with_connected_accounts": brands_with_connected_accounts,
            "industries_breakdown": industries_breakdown,
            "team_sizes_breakdown": team_sizes_breakdown,
        }

    @classmethod
    def _get_social_accounts_metrics(cls) -> dict:
        total_connected_accounts = SocialAccount.objects.count()

        platforms_breakdown = dict(
            SocialAccount.objects.values("platform")
            .annotate(count=Count("id"))
            .values_list("platform", "count")
        )

        return {
            "total_connected_accounts": total_connected_accounts,
            "platforms_breakdown": platforms_breakdown,
        }

    @classmethod
    def _get_posts_metrics(
        cls, *, start_of_today, seven_days_ago, thirty_days_ago
    ) -> dict:
        total_posts = ContentPost.objects.count()

        # Posts that have gone live: at least one platform entry has status='posted'
        live_posts_count = (
            ContentPost.objects.filter(platform_entries__status=PostStatus.POSTED)
            .distinct()
            .count()
        )

        # Total platform publications completed
        platform_posts_published = ContentPostPlatform.objects.filter(
            status=PostStatus.POSTED
        ).count()

        # Status breakdown of all platform entries
        raw_status_counts = dict(
            ContentPostPlatform.objects.values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )
        status_breakdown = {
            status_choice.value: raw_status_counts.get(status_choice.value, 0)
            for status_choice in PostStatus
        }

        # Content types breakdown (video, photo, text)
        content_types_breakdown = dict(
            ContentPost.objects.values("content_type")
            .annotate(count=Count("id"))
            .values_list("content_type", "count")
        )

        # Successfully published platform entries by platform
        published_by_platform = dict(
            ContentPostPlatform.objects.filter(status=PostStatus.POSTED)
            .values("platform")
            .annotate(count=Count("id"))
            .values_list("platform", "count")
        )

        # Creation activity
        posts_created_today = ContentPost.objects.filter(
            created_at__gte=start_of_today
        ).count()
        posts_created_this_week = ContentPost.objects.filter(
            created_at__gte=seven_days_ago
        ).count()
        posts_created_this_month = ContentPost.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()

        return {
            "total_posts": total_posts,
            "live_posts_count": live_posts_count,
            "platform_posts_published": platform_posts_published,
            "status_breakdown": status_breakdown,
            "content_types_breakdown": content_types_breakdown,
            "published_by_platform": published_by_platform,
            "activity": {
                "posts_created_today": posts_created_today,
                "posts_created_this_week": posts_created_this_week,
                "posts_created_this_month": posts_created_this_month,
            },
        }

    @classmethod
    def _get_storage_metrics(cls) -> dict:
        total_media_items = ContentMedia.objects.count()
        total_pending = PendingUpload.objects.count()
        claimed_pending = PendingUpload.objects.filter(is_claimed=True).count()
        unclaimed_pending = PendingUpload.objects.filter(is_claimed=False).count()

        return {
            "total_media_items": total_media_items,
            "pending_uploads": {
                "total": total_pending,
                "claimed": claimed_pending,
                "unclaimed": unclaimed_pending,
            },
        }
