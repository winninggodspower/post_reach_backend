from django.contrib import admin

from subscriptions.models import (
    PaymentTransaction,
    Subscription,
    SubscriptionPlan,
    WebhookEvent,
)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "tier",
        "price_usd",
        "price_ngn",
        "billing_interval",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active", "billing_interval", "tier")
    search_fields = ("name", "tier")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "status",
        "payment_method_type",
        "currency",
        "current_period_end",
        "cancel_at_period_end",
    )
    list_filter = ("status", "payment_method_type", "plan__tier")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "bachs_customer_id",
        "bachs_subscription_id",
    )


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user",
        "plan",
        "amount",
        "currency",
        "status",
        "payment_method",
        "created_at",
    )
    list_filter = ("status", "currency", "payment_method")
    search_fields = ("reference", "checkout_id", "charge_id", "user__email")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed", "created_at")
    list_filter = ("event_type", "processed")
    search_fields = ("event_id", "event_type")
