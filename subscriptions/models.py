from django.conf import settings
from django.db import models
from django.utils import timezone

from post_reach_backend.models import UUIDTimestampedModel
from subscriptions.enums import (
    BillingIntervalChoices,
    PaymentMethodChoices,
    PaymentMethodTypeChoices,
    PaymentTypeChoices,
    PlanTierChoices,
    SubscriptionStatusChoices,
    TransactionStatusChoices,
)


class SubscriptionPlan(UUIDTimestampedModel):
    tier = models.CharField(
        max_length=20,
        choices=PlanTierChoices.choices,
        unique=True,
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    price_ngn = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    billing_interval = models.CharField(
        max_length=20,
        choices=BillingIntervalChoices.choices,
        default=BillingIntervalChoices.MONTH,
    )
    bachs_product_id = models.CharField(max_length=100, blank=True, null=True)

    brands_limit = models.PositiveIntegerField(default=1)
    social_accounts_limit = models.PositiveIntegerField(default=3)
    monthly_platform_posts_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total platform posts per month across accounts (null represents unlimited).",
    )
    team_members_limit = models.PositiveIntegerField(default=1)
    has_content_calendar = models.BooleanField(default=True)
    has_advanced_analytics = models.BooleanField(default=False)
    ai_features = models.CharField(max_length=50, default="limited")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price_usd"]

    def __str__(self):
        return f"{self.name} (${self.price_usd} / ₦{self.price_ngn:,.0f})"


class Subscription(UUIDTimestampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatusChoices.choices,
        default=SubscriptionStatusChoices.ACTIVE,
    )
    billing_interval = models.CharField(
        max_length=20,
        choices=BillingIntervalChoices.choices,
        default=BillingIntervalChoices.MONTH,
    )
    payment_method_type = models.CharField(
        max_length=30,
        choices=PaymentMethodTypeChoices.choices,
        default=PaymentMethodTypeChoices.FREE,
    )
    currency = models.CharField(max_length=10, default="USD")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    bachs_customer_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
    )
    bachs_subscription_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
    )

    current_period_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of the current billing cycle.",
    )
    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the current billing period expires and access is re-evaluated or renewed.",
    )
    cancel_at_period_end = models.BooleanField(
        default=False,
        help_text="If true, the subscription remains active until current_period_end but will not auto-renew.",
    )
    canceled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"

    @property
    def is_valid_active(self) -> bool:
        if self.plan.tier == PlanTierChoices.FREE:
            return True
        if self.status in [
            SubscriptionStatusChoices.ACTIVE,
            SubscriptionStatusChoices.TRIALING,
        ]:
            if self.current_period_end is None:
                return True
            return self.current_period_end >= timezone.now()
        return False


class PaymentTransaction(UUIDTimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription_transactions",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=128, unique=True, db_index=True)
    checkout_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
    )
    checkout_url = models.URLField(max_length=1000, blank=True, null=True)
    charge_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10)
    status = models.CharField(
        max_length=30,
        choices=TransactionStatusChoices.choices,
        default=TransactionStatusChoices.PENDING,
    )
    payment_method = models.CharField(
        max_length=50,
        choices=PaymentMethodChoices.choices,
        default=PaymentMethodChoices.CARD,
    )
    payment_type = models.CharField(
        max_length=50,
        choices=PaymentTypeChoices.choices,
        default=PaymentTypeChoices.ONE_TIME,
    )
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount} {self.currency} [{self.status}]"


class WebhookEvent(UUIDTimestampedModel):
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    processed = models.BooleanField(default=True)
    payload = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.event_type} - {self.event_id}"
