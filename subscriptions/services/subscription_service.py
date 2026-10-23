import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from subscriptions.enums import (
    BillingIntervalChoices,
    PaymentMethodChoices,
    PaymentMethodTypeChoices,
    PaymentTypeChoices,
    PlanTierChoices,
    SubscriptionStatusChoices,
    TransactionStatusChoices,
)
from subscriptions.models import (
    PaymentTransaction,
    Subscription,
    SubscriptionPlan,
)
from subscriptions.services.bachs_service import BachsService
from users.models import User

logger = logging.getLogger(__name__)


class SubscriptionService:
    @classmethod
    def get_or_create_default_subscription(cls, user: User) -> Subscription:
        """
        Retrieves or creates the user's active subscription, defaulting to Free tier.
        """
        sub = Subscription.objects.select_related("plan").filter(user=user).first()
        if sub:
            # Check if non-free subscription expired
            if sub.plan.tier != PlanTierChoices.FREE:
                if sub.current_period_end and sub.current_period_end < timezone.now():
                    if sub.status == SubscriptionStatusChoices.ACTIVE:
                        sub.status = SubscriptionStatusChoices.EXPIRED
                        sub.save(update_fields=["status"])
            return sub

        free_plan = cls.get_plan_by_tier(PlanTierChoices.FREE)
        sub, _ = Subscription.objects.get_or_create(
            user=user,
            defaults={
                "plan": free_plan,
                "status": SubscriptionStatusChoices.ACTIVE,
                "payment_method_type": PaymentMethodTypeChoices.FREE,
                "currency": "USD",
                "amount": Decimal("0.00"),
            },
        )
        return sub

    @classmethod
    def get_plan_by_tier(cls, tier: str) -> SubscriptionPlan:
        plan = SubscriptionPlan.objects.filter(tier=tier, is_active=True).first()
        if not plan:
            cls.seed_default_plans()
            plan = SubscriptionPlan.objects.filter(tier=tier, is_active=True).first()
            if not plan:
                raise ValueError(f"Subscription plan for tier '{tier}' does not exist.")
        return plan

    @classmethod
    def get_all_plans(cls):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "price_usd")
        if not plans.exists():
            cls.seed_default_plans()
            plans = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "price_usd")
        return plans

    @classmethod
    def create_checkout_session(
        cls,
        user: User,
        plan_tier: str,
        currency: str = "USD",
        payment_method_type: str = "auto",
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a checkout session for the user to subscribe to a paid plan.
        Supports bank transfer / money transfer (NGN) and card (USD).
        """
        if plan_tier == PlanTierChoices.FREE:
            raise ValueError("The Free plan does not require a checkout session.")

        plan = cls.get_plan_by_tier(plan_tier)
        currency = currency.upper()

        if currency == "NGN":
            amount = plan.price_ngn
            payment_type = PaymentTypeChoices.ONE_TIME
            if payment_method_type == "bank_transfer":
                payment_method = PaymentMethodChoices.NGN_BANK_TRANSFER
            elif payment_method_type == "card":
                payment_method = PaymentMethodChoices.CARD
            else:
                payment_method = PaymentMethodChoices.UNKNOWN
        else:
            currency = "USD"
            amount = plan.price_usd
            payment_type = (
                PaymentTypeChoices.RECURRING
                if plan.bachs_product_id
                else PaymentTypeChoices.ONE_TIME
            )
            payment_method = PaymentMethodChoices.CARD

        reference = f"sub_{user.id}_{int(timezone.now().timestamp())}_{uuid.uuid4().hex[:6]}"

        checkout_data = BachsService.create_checkout_session(
            user=user,
            plan=plan,
            currency=currency,
            payment_method_type=payment_method_type,
            success_url=success_url,
            cancel_url=cancel_url,
            reference=reference,
        )

        checkout_id = checkout_data.get("checkout_id")
        checkout_url = checkout_data.get("checkout_url")

        PaymentTransaction.objects.create(
            user=user,
            plan=plan,
            reference=reference,
            checkout_id=checkout_id,
            checkout_url=checkout_url,
            amount=amount,
            currency=currency,
            status=TransactionStatusChoices.PENDING,
            payment_type=payment_type,
            payment_method=payment_method,
            metadata={
                "plan_tier": plan.tier,
                "payment_method_type": payment_method_type,
            },
        )

        return {
            "checkout_id": checkout_id,
            "checkout_url": checkout_url,
            "reference": reference,
            "currency": currency,
            "amount": str(amount),
            "plan_tier": plan.tier,
        }

    @classmethod
    def create_customer_portal_session(cls, user: User) -> Dict[str, Any]:
        """
        Creates a portal session for customer to manage cards and invoices.
        """
        sub = cls.get_or_create_default_subscription(user)
        if not sub.bachs_customer_id:
            raise ValueError("No Bachs customer record found for this subscription.")

        return BachsService.create_customer_portal_session(sub.bachs_customer_id)

    @classmethod
    def cancel_user_subscription(
        cls, user: User, cancel_at_period_end: bool = True
    ) -> Subscription:
        """
        Cancels the user's active paid subscription.
        """
        sub = cls.get_or_create_default_subscription(user)
        if sub.plan.tier == PlanTierChoices.FREE:
            return sub

        if sub.bachs_subscription_id:
            try:
                BachsService.cancel_subscription(
                    sub.bachs_subscription_id,
                    cancel_at_period_end=cancel_at_period_end,
                )
            except Exception as e:
                logger.warning(
                    f"Could not cancel Bachs subscription {sub.bachs_subscription_id}: {e}"
                )

        if cancel_at_period_end:
            sub.cancel_at_period_end = True
            sub.save(update_fields=["cancel_at_period_end"])
        else:
            free_plan = cls.get_plan_by_tier(PlanTierChoices.FREE)
            sub.plan = free_plan
            sub.status = SubscriptionStatusChoices.CANCELED
            sub.canceled_at = timezone.now()
            sub.cancel_at_period_end = False
            sub.save(
                update_fields=[
                    "plan",
                    "status",
                    "canceled_at",
                    "cancel_at_period_end",
                ]
            )

        return sub



    @classmethod
    def seed_default_plans(cls):
        """
        Seeds the 3 Postglee plans:
        1. Free: $0 / ₦0
        2. Pro: $5 / ₦5,000
        3. Enterprise: $12 / ₦14,000
        """
        plans_data = [
            {
                "tier": PlanTierChoices.FREE,
                "name": "Free",
                "description": "Essential tools to start growing your presence",
                "price_usd": Decimal("0.00"),
                "price_ngn": Decimal("0.00"),
                "billing_interval": BillingIntervalChoices.MONTH,
                "brands_limit": 1,
                "social_accounts_limit": 3,
                "monthly_platform_posts_limit": 30,
                "team_members_limit": 1,
                "has_content_calendar": True,
                "has_advanced_analytics": False,
                "ai_features": "limited",
                "sort_order": 0,
            },
            {
                "tier": PlanTierChoices.PRO,
                "name": "Pro",
                "description": "Powerful tools and multi-account publishing for growing brands",
                "price_usd": Decimal("5.00"),
                "price_ngn": Decimal("5000.00"),
                "billing_interval": BillingIntervalChoices.MONTH,
                "brands_limit": 2,
                "social_accounts_limit": 10,
                "monthly_platform_posts_limit": None,  # Unlimited
                "team_members_limit": 3,
                "has_content_calendar": True,
                "has_advanced_analytics": True,
                "ai_features": "full",
                "sort_order": 1,
            },
            {
                "tier": PlanTierChoices.ENTERPRISE,
                "name": "Enterprise",
                "description": "Maximum power, workflows, analytics and team collaboration",
                "price_usd": Decimal("12.00"),
                "price_ngn": Decimal("14000.00"),
                "billing_interval": BillingIntervalChoices.MONTH,
                "brands_limit": 10,
                "social_accounts_limit": 50,
                "monthly_platform_posts_limit": None,  # Unlimited
                "team_members_limit": 10,
                "has_content_calendar": True,
                "has_advanced_analytics": True,
                "ai_features": "full",
                "sort_order": 2,
            },
        ]

        for pdata in plans_data:
            SubscriptionPlan.objects.update_or_create(
                tier=pdata["tier"],
                defaults=pdata,
            )
