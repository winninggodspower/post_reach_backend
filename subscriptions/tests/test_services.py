from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from django.utils import timezone

from subscriptions.enums import (
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
from subscriptions.services import BachsService, SubscriptionService, WebhookService


@pytest.mark.django_db
def test_get_or_create_default_subscription(user):
    sub = SubscriptionService.get_or_create_default_subscription(user)
    assert sub.user == user
    assert sub.plan.tier == PlanTierChoices.FREE
    assert sub.status == SubscriptionStatusChoices.ACTIVE
    assert sub.is_valid_active is True


@pytest.mark.django_db
def test_get_all_plans():
    plans = SubscriptionService.get_all_plans()
    assert plans.count() == 3
    tiers = [p.tier for p in plans]
    assert tiers == [PlanTierChoices.FREE, PlanTierChoices.PRO, PlanTierChoices.ENTERPRISE]

    pro = plans.get(tier=PlanTierChoices.PRO)
    assert pro.price_usd == Decimal("5.00")
    assert pro.price_ngn == Decimal("5000.00")

    enterprise = plans.get(tier=PlanTierChoices.ENTERPRISE)
    assert enterprise.price_usd == Decimal("12.00")
    assert enterprise.price_ngn == Decimal("14000.00")


@pytest.mark.django_db
def test_create_checkout_session_card(user, mocker):
    mocker.patch.object(
        BachsService,
        "create_checkout_session",
        return_value={
            "checkout_id": "chk_test123",
            "checkout_url": "https://checkout.bachs.io/c/test123",
            "status": "open",
        },
    )

    result = SubscriptionService.create_checkout_session(
        user=user,
        plan_tier=PlanTierChoices.PRO,
        currency="USD",
        payment_method_type="card",
    )

    assert result["checkout_id"] == "chk_test123"
    assert result["checkout_url"] == "https://checkout.bachs.io/c/test123"
    assert result["currency"] == "USD"
    assert result["amount"] == "5.00"

    tx = PaymentTransaction.objects.get(reference=result["reference"])
    assert tx.checkout_id == "chk_test123"
    assert tx.status == TransactionStatusChoices.PENDING
    assert tx.payment_method == "CARD"


@pytest.mark.django_db
def test_create_checkout_session_bank_transfer(user, mocker):
    mocker.patch.object(
        BachsService,
        "create_checkout_session",
        return_value={
            "checkout_id": "chk_bank456",
            "checkout_url": "https://checkout.bachs.io/c/bank456",
            "status": "open",
        },
    )

    result = SubscriptionService.create_checkout_session(
        user=user,
        plan_tier=PlanTierChoices.ENTERPRISE,
        currency="NGN",
        payment_method_type="bank_transfer",
    )

    assert result["checkout_id"] == "chk_bank456"
    assert result["currency"] == "NGN"
    assert result["amount"] == "14000.00"

    tx = PaymentTransaction.objects.get(reference=result["reference"])
    assert tx.checkout_id == "chk_bank456"
    assert tx.payment_method == "NGN_BANK_TRANSFER"


@pytest.mark.django_db
def test_webhook_collection_succeeded_bank_transfer(user):
    # Setup pending transaction
    plan = SubscriptionService.get_plan_by_tier(PlanTierChoices.PRO)
    PaymentTransaction.objects.create(
        user=user,
        plan=plan,
        reference="sub_ref_123",
        checkout_id="chk_bank_999",
        amount=Decimal("5000.00"),
        currency="NGN",
        status=TransactionStatusChoices.PENDING,
    )

    event_payload = {
        "id": "evt_collect_001",
        "type": "collection.succeeded",
        "data": {
            "charge_id": "ch_999",
            "checkout_id": "chk_bank_999",
            "amount": "5000.00",
            "currency": "NGN",
            "metadata": {
                "user_id": str(user.id),
                "plan_tier": PlanTierChoices.PRO,
            },
            "payment_method_details": {
                "type": "bank_transfer",
            },
        },
    }

    success, msg = WebhookService.process_webhook_event(event_payload)
    assert success is True

    # User subscription must now be active Pro plan via bank transfer
    sub = Subscription.objects.get(user=user)
    assert sub.plan.tier == PlanTierChoices.PRO
    assert sub.status == SubscriptionStatusChoices.ACTIVE
    assert sub.payment_method_type == PaymentMethodTypeChoices.BANK_TRANSFER
    assert sub.currency == "NGN"
    assert sub.amount == Decimal("5000.00")
    assert sub.current_period_end is not None
    assert sub.current_period_end > timezone.now()

    # Transaction must be marked succeeded
    tx = PaymentTransaction.objects.get(checkout_id="chk_bank_999")
    assert tx.status == TransactionStatusChoices.SUCCEEDED
    assert tx.charge_id == "ch_999"

    # Idempotency check: sending same event again should be ignored
    success2, msg2 = WebhookService.process_webhook_event(event_payload)
    assert success2 is True
    assert "already processed" in msg2


@pytest.mark.django_db
def test_webhook_subscription_lifecycle(user):
    sub_created_event = {
        "id": "evt_sub_create_123",
        "type": "customer.subscription.created",
        "data": {
            "subscription_id": "sub_bachs_888",
            "status": "active",
            "currency": "USD",
            "amount": "12.00",
            "customer": {
                "customer_id": "cust_bachs_111",
                "email": user.email,
            },
            "metadata": {
                "user_id": str(user.id),
                "plan_tier": PlanTierChoices.ENTERPRISE,
            },
            "current_period_start": "2026-10-01T00:00:00Z",
            "current_period_end": "2026-11-01T00:00:00Z",
            "cancel_at_period_end": False,
        },
    }

    success, _ = WebhookService.process_webhook_event(sub_created_event)
    assert success is True

    sub = Subscription.objects.get(user=user)
    assert sub.plan.tier == PlanTierChoices.ENTERPRISE
    assert sub.bachs_subscription_id == "sub_bachs_888"
    assert sub.bachs_customer_id == "cust_bachs_111"
    assert sub.status == SubscriptionStatusChoices.ACTIVE

    # Test subscription deletion
    sub_deleted_event = {
        "id": "evt_sub_del_456",
        "type": "customer.subscription.deleted",
        "data": {
            "subscription_id": "sub_bachs_888",
        },
    }

    success_del, _ = WebhookService.process_webhook_event(sub_deleted_event)
    assert success_del is True

    sub.refresh_from_db()
    assert sub.status == SubscriptionStatusChoices.CANCELED
    assert sub.plan.tier == PlanTierChoices.FREE


@pytest.mark.django_db
def test_cancel_user_subscription(user, mocker):
    mocker.patch.object(BachsService, "cancel_subscription", return_value=True)

    plan = SubscriptionService.get_plan_by_tier(PlanTierChoices.PRO)
    sub = SubscriptionService.get_or_create_default_subscription(user)
    sub.plan = plan
    sub.status = SubscriptionStatusChoices.ACTIVE
    sub.bachs_subscription_id = "sub_bachs_999"
    sub.save()

    # Cancel at period end
    updated_sub = SubscriptionService.cancel_user_subscription(user, cancel_at_period_end=True)
    assert updated_sub.cancel_at_period_end is True

    # Immediate cancel
    updated_sub2 = SubscriptionService.cancel_user_subscription(user, cancel_at_period_end=False)
    assert updated_sub2.status == SubscriptionStatusChoices.CANCELED
    assert updated_sub2.plan.tier == PlanTierChoices.FREE
