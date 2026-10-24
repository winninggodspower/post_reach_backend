from django.urls import path

from subscriptions.views import (
    BachsWebhookView,
    CancelSubscriptionView,
    CreateCheckoutSessionView,
    CustomerPortalView,
    SubscriptionPlansView,
    UserSubscriptionView,
)

urlpatterns = [
    path("plans/", SubscriptionPlansView.as_view(), name="subscription-plans"),
    path("me/", UserSubscriptionView.as_view(), name="subscription-me"),
    path(
        "checkout/", CreateCheckoutSessionView.as_view(), name="subscription-checkout"
    ),
    path("portal/", CustomerPortalView.as_view(), name="subscription-portal"),
    path("cancel/", CancelSubscriptionView.as_view(), name="subscription-cancel"),
    path(
        "webhooks/bachs/", BachsWebhookView.as_view(), name="subscription-bachs-webhook"
    ),
]
