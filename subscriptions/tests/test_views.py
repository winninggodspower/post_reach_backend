from decimal import Decimal

import pytest
from django.urls import reverse

from subscriptions.enums import PlanTierChoices, SubscriptionStatusChoices
from subscriptions.models import Subscription, SubscriptionPlan
from subscriptions.services import BachsService, SubscriptionService


@pytest.mark.django_db
def test_get_plans_endpoint(api_client):
    url = reverse("subscription-plans")
    response = api_client.get(url)

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    plans = res_data["data"]
    assert len(plans) == 7

    tiers = {p["tier"] for p in plans}
    assert tiers == {"free", "starter", "creator", "agency"}
    intervals = {p["billing_interval"] for p in plans}
    assert intervals == {"month", "year"}


@pytest.mark.django_db
def test_get_my_subscription_unauthenticated(api_client):
    url = reverse("subscription-me")
    response = api_client.get(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_get_my_subscription_authenticated(authenticated_client, user):
    url = reverse("subscription-me")
    response = authenticated_client.get(url)

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    data = res_data["data"]
    assert data["plan"]["tier"] == "free"
    assert data["status"] == "active"
    assert data["is_valid_active"] is True


@pytest.mark.django_db
def test_checkout_endpoint_card(authenticated_client, user, mocker):
    mocker.patch.object(
        BachsService,
        "create_checkout_session",
        return_value={
            "checkout_id": "chk_api_123",
            "checkout_url": "https://checkout.bachs.io/c/api_123",
            "status": "open",
        },
    )

    url = reverse("subscription-checkout")
    payload = {
        "plan_tier": "starter",
        "currency": "USD",
        "payment_method": "card",
        "success_url": "https://app.postglee.com/billing/success",
        "cancel_url": "https://app.postglee.com/pricing",
    }
    response = authenticated_client.post(url, payload, format="json")

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["checkout_id"] == "chk_api_123"
    assert res_data["data"]["checkout_url"] == "https://checkout.bachs.io/c/api_123"
    assert res_data["data"]["amount"] == "6.00"
    assert res_data["data"]["currency"] == "USD"


@pytest.mark.django_db
def test_checkout_endpoint_bank_transfer(authenticated_client, user, mocker):
    mocker.patch.object(
        BachsService,
        "create_checkout_session",
        return_value={
            "checkout_id": "chk_api_transfer_456",
            "checkout_url": "https://checkout.bachs.io/c/transfer_456",
            "status": "open",
        },
    )

    url = reverse("subscription-checkout")
    payload = {
        "plan_tier": "creator",
        "currency": "NGN",
        "payment_method": "bank_transfer",
    }
    response = authenticated_client.post(url, payload, format="json")

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["data"]["amount"] == "14000.00"
    assert res_data["data"]["currency"] == "NGN"


@pytest.mark.django_db
def test_checkout_endpoint_free_rejected(authenticated_client):
    url = reverse("subscription-checkout")
    payload = {"plan_tier": "free"}
    response = authenticated_client.post(url, payload, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_customer_portal_endpoint(authenticated_client, user, mocker):
    mocker.patch.object(
        BachsService,
        "create_customer_portal_session",
        return_value={"id": "psn_123", "url": "https://portal.bachs.io/s/test"},
    )

    sub = SubscriptionService.get_or_create_default_subscription(user)
    sub.bachs_customer_id = "cust_test_123"
    sub.save()

    url = reverse("subscription-portal")
    response = authenticated_client.post(url)

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["data"]["portal_url"] == "https://portal.bachs.io/s/test"


@pytest.mark.django_db
def test_cancel_subscription_endpoint(authenticated_client, user, mocker):
    mocker.patch.object(BachsService, "cancel_subscription", return_value=True)

    plan = SubscriptionService.get_plan_by_tier(PlanTierChoices.STARTER)
    sub = SubscriptionService.get_or_create_default_subscription(user)
    sub.plan = plan
    sub.status = SubscriptionStatusChoices.ACTIVE
    sub.bachs_subscription_id = "sub_bachs_api_999"
    sub.save()

    url = reverse("subscription-cancel")
    response = authenticated_client.post(
        url, {"cancel_at_period_end": True}, format="json"
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["data"]["cancel_at_period_end"] is True


@pytest.mark.django_db
def test_bachs_webhook_view_signature_error(api_client, mocker):
    from bachs import BachsWebhookError

    mocker.patch.object(
        BachsService,
        "verify_and_construct_webhook_event",
        side_effect=BachsWebhookError("Invalid signature"),
    )

    url = reverse("subscription-bachs-webhook")
    response = api_client.post(
        url,
        data='{"id": "evt_test"}',
        content_type="application/json",
        HTTP_X_BACHS_SIGNATURE_V2="invalid_sig",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_bachs_webhook_view_valid_event(api_client, user, mocker):
    mock_event = {
        "id": "evt_endpoint_test_001",
        "type": "collection.succeeded",
        "data": {
            "charge_id": "ch_endpoint_1",
            "amount": "5000.00",
            "currency": "NGN",
            "metadata": {
                "user_id": str(user.id),
                "plan_tier": "starter",
            },
            "payment_method_details": {
                "type": "bank_transfer",
            },
        },
    }
    mocker.patch.object(
        BachsService,
        "verify_and_construct_webhook_event",
        return_value=mock_event,
    )

    url = reverse("subscription-bachs-webhook")
    response = api_client.post(
        url,
        data='{"id": "evt_endpoint_test_001"}',
        content_type="application/json",
        HTTP_X_BACHS_SIGNATURE_V2="t=1700000000,v1=valid",
    )

    assert response.status_code == 200

    sub = Subscription.objects.get(user=user)
    assert sub.plan.tier == "starter"
    assert sub.status == "active"
