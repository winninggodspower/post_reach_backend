from rest_framework import serializers


class UserGrowthSerializer(serializers.Serializer):
    joined_today = serializers.IntegerField()
    joined_this_week = serializers.IntegerField()
    joined_this_month = serializers.IntegerField()


class UserAnalyticsSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    completed_onboarding = serializers.IntegerField()
    pending_onboarding = serializers.IntegerField()
    onboarding_completion_rate_percentage = serializers.FloatField()
    roles_breakdown = serializers.DictField(child=serializers.IntegerField())
    growth = UserGrowthSerializer()


class BrandAnalyticsSerializer(serializers.Serializer):
    total_brands = serializers.IntegerField()
    brands_with_connected_accounts = serializers.IntegerField()
    industries_breakdown = serializers.DictField(child=serializers.IntegerField())
    team_sizes_breakdown = serializers.DictField(child=serializers.IntegerField())


class SocialAccountAnalyticsSerializer(serializers.Serializer):
    total_connected_accounts = serializers.IntegerField()
    platforms_breakdown = serializers.DictField(child=serializers.IntegerField())


class PostActivitySerializer(serializers.Serializer):
    posts_created_today = serializers.IntegerField()
    posts_created_this_week = serializers.IntegerField()
    posts_created_this_month = serializers.IntegerField()


class ContentPostAnalyticsSerializer(serializers.Serializer):
    total_posts = serializers.IntegerField()
    live_posts_count = serializers.IntegerField()
    platform_posts_published = serializers.IntegerField()
    status_breakdown = serializers.DictField(child=serializers.IntegerField())
    content_types_breakdown = serializers.DictField(child=serializers.IntegerField())
    published_by_platform = serializers.DictField(child=serializers.IntegerField())
    activity = PostActivitySerializer()


class PendingUploadsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    claimed = serializers.IntegerField()
    unclaimed = serializers.IntegerField()


class StorageAnalyticsSerializer(serializers.Serializer):
    total_media_items = serializers.IntegerField()
    pending_uploads = PendingUploadsSerializer()


class AdminAnalyticsSummarySerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    completed_onboarding = serializers.IntegerField()
    onboarding_completion_rate_percentage = serializers.FloatField()
    total_connected_accounts = serializers.IntegerField()
    live_posts_count = serializers.IntegerField()
    total_posts = serializers.IntegerField()
    failed_posts_count = serializers.IntegerField()


class AdminAnalyticsSummaryResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = AdminAnalyticsSummarySerializer()


class AdminAnalyticsOverviewSerializer(serializers.Serializer):
    summary = AdminAnalyticsSummarySerializer()
    users = UserAnalyticsSerializer()
    brands = BrandAnalyticsSerializer()
    social_accounts = SocialAccountAnalyticsSerializer()
    posts = ContentPostAnalyticsSerializer()
    storage = StorageAnalyticsSerializer()


class AdminAnalyticsResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = AdminAnalyticsOverviewSerializer()
