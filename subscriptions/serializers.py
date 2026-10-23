from rest_framework import serializers

from subscriptions.enums import PlanTierChoices
from subscriptions.models import Subscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "tier",
            "name",
            "description",
            "price_usd",
            "price_ngn",
            "billing_interval",
            "brands_limit",
            "social_accounts_limit",
            "monthly_platform_posts_limit",
            "team_members_limit",
            "has_content_calendar",
            "has_advanced_analytics",
            "ai_features",
        ]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    is_valid_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "is_valid_active",
            "billing_interval",
            "payment_method_type",
            "currency",
            "amount",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
        ]
        read_only_fields = fields


class CheckoutSessionRequestSerializer(serializers.Serializer):
    plan_tier = serializers.ChoiceField(
        choices=[PlanTierChoices.PRO, PlanTierChoices.ENTERPRISE]
    )
    currency = serializers.ChoiceField(choices=["USD", "NGN"], default="USD")
    payment_method = serializers.ChoiceField(
        choices=["card", "bank_transfer", "auto"],
        default="auto",
        help_text="'card' for USD card, 'bank_transfer' for NGN money transfer, or 'auto'.",
    )
    success_url = serializers.URLField(required=False, allow_blank=True)
    cancel_url = serializers.URLField(required=False, allow_blank=True)


class CheckoutSessionResponseSerializer(serializers.Serializer):
    checkout_id = serializers.CharField()
    checkout_url = serializers.URLField()
    reference = serializers.CharField()
    currency = serializers.CharField()
    amount = serializers.CharField()
    plan_tier = serializers.CharField()


class CustomerPortalResponseSerializer(serializers.Serializer):
    portal_url = serializers.URLField()


class CancelSubscriptionRequestSerializer(serializers.Serializer):
    cancel_at_period_end = serializers.BooleanField(
        default=True,
        help_text="If True, keeps plan active until period end without renewal; if False, cancels immediately.",
    )
