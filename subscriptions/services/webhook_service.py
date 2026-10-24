import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Tuple

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from subscriptions.enums import (
    BillingIntervalChoices,
    PaymentMethodChoices,
    PaymentMethodTypeChoices,
    PlanTierChoices,
    SubscriptionStatusChoices,
    TransactionStatusChoices,
)
from subscriptions.models import (
    PaymentTransaction,
    Subscription,
    SubscriptionPlan,
    WebhookEvent,
)
from users.models import User

logger = logging.getLogger(__name__)


class WebhookService:
    """
    Handles processing of incoming webhook events from Bachs.
    """

    @classmethod
    @transaction.atomic
    def process_webhook_event(cls, event: Any) -> tuple[bool, str]:
        """
        Processes webhook events from Bachs idempotently.
        """
        event_id = getattr(event, "id", None) or (
            event.get("id") if isinstance(event, dict) else None
        )
        event_type = getattr(event, "type", None) or (
            event.get("type") if isinstance(event, dict) else None
        )

        if not event_id or not event_type:
            return False, "Malformed event missing id or type"

        if WebhookEvent.objects.filter(event_id=event_id).exists():
            return True, "Event already processed"

        data = getattr(event, "data", None) or (
            event.get("data") if isinstance(event, dict) else {}
        )
        if hasattr(data, "to_dict"):
            data_dict = data.to_dict()
        elif hasattr(data, "__dict__"):
            data_dict = vars(data)
        elif isinstance(data, dict):
            data_dict = data
        else:
            data_dict = {}

        WebhookEvent.objects.create(
            event_id=event_id,
            event_type=event_type,
            processed=True,
            payload=data_dict,
        )

        if event_type == "collection.succeeded":
            cls._handle_collection_succeeded(data_dict)
        elif event_type in [
            "customer.subscription.created",
            "customer.subscription.updated",
        ]:
            cls._handle_subscription_sync(data_dict)
        elif event_type == "customer.subscription.deleted":
            cls._handle_subscription_deleted(data_dict)
        elif event_type == "invoice.paid":
            cls._handle_invoice_paid(data_dict)
        elif event_type == "invoice.payment_failed":
            cls._handle_invoice_payment_failed(data_dict)

        return True, "Event processed successfully"

    @classmethod
    def _handle_collection_succeeded(cls, data: dict[str, Any]):
        """
        Handles payment collection succeeded. This is critical for Bank Transfer (money transfer)
        and one-time payments.
        """
        from subscriptions.services.subscription_service import SubscriptionService

        checkout_id = data.get("checkout_id")
        charge_id = data.get("charge_id")
        amount = data.get("amount")
        currency = data.get("currency", "NGN")
        metadata = data.get("metadata", {}) or {}

        transaction_obj = None
        if checkout_id:
            transaction_obj = PaymentTransaction.objects.filter(
                checkout_id=checkout_id
            ).first()

        user = None
        user_id = metadata.get("user_id")
        if user_id:
            user = User.objects.filter(id=user_id).first()

        if not user and transaction_obj:
            user = transaction_obj.user

        plan_tier = metadata.get("plan_tier")
        if not plan_tier and transaction_obj and transaction_obj.plan:
            plan_tier = transaction_obj.plan.tier

        if transaction_obj:
            transaction_obj.status = TransactionStatusChoices.SUCCEEDED
            transaction_obj.charge_id = charge_id
            payment_details = data.get("payment_method_details", {}) or {}
            method_str = str(
                payment_details.get("type") or data.get("payment_method") or ""
            ).upper()
            if "BANK_TRANSFER" in method_str:
                transaction_obj.payment_method = PaymentMethodChoices.NGN_BANK_TRANSFER
            elif "CARD" in method_str:
                transaction_obj.payment_method = PaymentMethodChoices.CARD
            else:
                transaction_obj.payment_method = PaymentMethodChoices.UNKNOWN
            transaction_obj.save()

        if user and plan_tier:
            plan = SubscriptionService.get_plan_by_tier(plan_tier)
            now = timezone.now()
            if plan.billing_interval == BillingIntervalChoices.YEAR:
                period_end = now + timedelta(days=365)
            else:
                period_end = now + timedelta(days=30)

            sub = SubscriptionService.get_or_create_default_subscription(user)
            sub.plan = plan
            sub.status = SubscriptionStatusChoices.ACTIVE
            sub.currency = currency
            if amount:
                sub.amount = Decimal(str(amount))
            sub.current_period_start = now
            sub.current_period_end = period_end
            sub.payment_method_type = (
                PaymentMethodTypeChoices.BANK_TRANSFER
                if "bank_transfer" in str(data).lower()
                else PaymentMethodTypeChoices.CARD
            )
            sub.cancel_at_period_end = False
            sub.save()
            logger.info(
                f"Activated {plan.name} subscription for user {user.email} via collection.succeeded"
            )

    @classmethod
    def _handle_subscription_sync(cls, data: dict[str, Any]):
        """
        Handles recurring Bachs subscription created/updated.
        """
        from subscriptions.services.subscription_service import SubscriptionService

        sub_id = data.get("subscription_id") or data.get("id")
        customer = data.get("customer") or {}
        customer_id = customer.get("customer_id") or data.get("customer_id")
        customer_email = customer.get("email")

        metadata = data.get("metadata", {}) or {}
        user_id = metadata.get("user_id")

        user = None
        if user_id:
            user = User.objects.filter(id=user_id).first()
        if not user and customer_email:
            user = User.objects.filter(email=customer_email).first()

        if not user:
            logger.warning(f"Could not link subscription event {sub_id} to a user.")
            return

        plan_tier = metadata.get("plan_tier")
        plan = None
        if plan_tier:
            plan = SubscriptionService.get_plan_by_tier(plan_tier)
        elif data.get("product_id"):
            plan = SubscriptionPlan.objects.filter(
                bachs_product_id=data.get("product_id")
            ).first()

        if not plan:
            plan = SubscriptionService.get_plan_by_tier(PlanTierChoices.STARTER)

        status = data.get("status", "active")
        status_map = {
            "trialing": SubscriptionStatusChoices.TRIALING,
            "active": SubscriptionStatusChoices.ACTIVE,
            "past_due": SubscriptionStatusChoices.PAST_DUE,
            "unpaid": SubscriptionStatusChoices.UNPAID,
            "canceled": SubscriptionStatusChoices.CANCELED,
        }
        db_status = status_map.get(status, SubscriptionStatusChoices.ACTIVE)

        sub = SubscriptionService.get_or_create_default_subscription(user)
        sub.plan = plan
        sub.status = db_status
        sub.bachs_subscription_id = sub_id
        if customer_id:
            sub.bachs_customer_id = customer_id
        sub.payment_method_type = PaymentMethodTypeChoices.CARD
        sub.currency = data.get("currency", "USD")
        if data.get("amount"):
            sub.amount = Decimal(str(data.get("amount")))

        period_start = data.get("current_period_start")
        period_end = data.get("current_period_end")
        if period_start:
            sub.current_period_start = parse_datetime(period_start)
        if period_end:
            sub.current_period_end = parse_datetime(period_end)

        sub.cancel_at_period_end = bool(data.get("cancel_at_period_end", False))
        sub.save()
        logger.info(
            f"Synchronized recurring subscription {sub_id} for user {user.email}"
        )

    @classmethod
    def _handle_subscription_deleted(cls, data: dict[str, Any]):
        """
        Handles cancelled / deleted recurring subscription.
        """
        from subscriptions.services.subscription_service import SubscriptionService

        sub_id = data.get("subscription_id") or data.get("id")
        sub = Subscription.objects.filter(bachs_subscription_id=sub_id).first()
        if sub:
            free_plan = SubscriptionService.get_plan_by_tier(PlanTierChoices.FREE)
            sub.plan = free_plan
            sub.status = SubscriptionStatusChoices.CANCELED
            sub.canceled_at = timezone.now()
            sub.cancel_at_period_end = False
            sub.save()
            logger.info(f"Canceled subscription {sub_id} for user {sub.user.email}")

    @classmethod
    def _handle_invoice_paid(cls, data: dict[str, Any]):
        """
        Extends subscription period upon successful invoice payment.
        """
        sub_id = data.get("subscription_id")
        if sub_id:
            sub = Subscription.objects.filter(bachs_subscription_id=sub_id).first()
            if sub:
                sub.status = SubscriptionStatusChoices.ACTIVE
                period_end = data.get("period_end") or data.get("next_billed_at")
                if period_end:
                    sub.current_period_end = parse_datetime(period_end)
                sub.save(update_fields=["status", "current_period_end"])

    @classmethod
    def _handle_invoice_payment_failed(cls, data: dict[str, Any]):
        """
        Marks subscription as past due upon failed renewal attempt.
        """
        sub_id = data.get("subscription_id")
        if sub_id:
            sub = Subscription.objects.filter(bachs_subscription_id=sub_id).first()
            if sub:
                sub.status = SubscriptionStatusChoices.PAST_DUE
                sub.save(update_fields=["status"])
