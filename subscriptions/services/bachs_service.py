import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class BachsService:
    @classmethod
    def get_api_key(cls) -> str:
        return getattr(settings, "BACHS_API_KEY", "")

    @classmethod
    def get_webhook_secret(cls) -> str:
        return getattr(settings, "BACHS_WEBHOOK_SECRET", "")

    @classmethod
    def get_client(cls):
        from bachs import Bachs

        api_key = cls.get_api_key()
        if not api_key:
            raise ValueError("BACHS_API_KEY is not configured in settings.")
        return Bachs(api_key=api_key)

    @classmethod
    def create_checkout_session(
        cls,
        user,
        plan,
        currency: str = "USD",
        payment_method_type: str = "auto",
        success_url: str | None = None,
        cancel_url: str | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Creates a Bachs Checkout Session.
        Supports both USD Card (recurring subscription) and NGN Money Transfer (bank transfer).
        """
        client = cls.get_client()

        customer = {
            "email": user.email,
            "name": (user.get_full_name().strip() or user.handle or user.email),
        }

        metadata = {
            "user_id": str(user.id),
            "plan_tier": plan.tier,
            "billing_interval": plan.billing_interval,
            "currency": currency,
            "payment_method_type": payment_method_type,
        }

        checkout_kwargs: dict[str, Any] = {
            "customer": customer,
            "metadata": metadata,
        }

        if reference:
            checkout_kwargs["reference"] = reference

        if success_url:
            checkout_kwargs["success_url"] = success_url
        if cancel_url:
            checkout_kwargs["cancel_url"] = cancel_url

        amount = plan.price_ngn if currency == "NGN" else plan.price_usd

        if plan.bachs_product_id:
            cart_item: dict[str, Any] = {
                "product_id": plan.bachs_product_id,
                "quantity": 1,
            }
            if currency == "NGN":
                cart_item["pricing"] = {
                    "currency": "NGN",
                    "amount": f"{amount:.2f}",
                }
            checkout_kwargs["product_cart"] = [cart_item]
            checkout_kwargs["billing_currency"] = currency
        else:
            checkout_kwargs["pricing"] = {
                "currency": currency,
                "amount": f"{amount:.2f}",
            }

        # Restrict payment rail only when explicitly requested; otherwise 'auto' lets Bachs present all options
        if payment_method_type == "bank_transfer":
            checkout_kwargs["payment_method_types"] = ["NGN_BANK_TRANSFER"]
        elif payment_method_type == "card":
            checkout_kwargs["payment_method_types"] = [f"{currency}_CARD"]

        checkout = client.checkout_sessions.create(**checkout_kwargs)

        return {
            "checkout_id": getattr(checkout, "id", None)
            or getattr(checkout, "checkout_id", None),
            "checkout_url": getattr(checkout, "checkout_url", None),
            "status": getattr(checkout, "status", "open"),
            "expires_at": getattr(checkout, "expires_at", None),
        }

    @classmethod
    def create_customer_portal_session(cls, customer_id: str) -> dict[str, Any]:
        """
        Creates a customer portal session on Bachs for managing recurring subscriptions.
        """
        client = cls.get_client()
        session = client.customer_portal.create_session(customer_id)
        return {
            "id": getattr(session, "id", None),
            "url": getattr(session, "url", None),
        }

    @classmethod
    def cancel_subscription(
        cls, subscription_id: str, cancel_at_period_end: bool = True
    ) -> Any:
        """
        Cancels a subscription through Bachs API.
        """
        client = cls.get_client()
        return client.subscriptions.cancel(
            subscription_id, cancel_at_period_end=cancel_at_period_end
        )

    @classmethod
    def verify_and_construct_webhook_event(
        cls, raw_body: bytes, headers: dict[str, Any]
    ) -> Any:
        """
        Verifies Bachs webhook signature and returns the event object.
        """
        from bachs import webhooks

        secret = cls.get_webhook_secret()
        if not secret:
            raise ValueError("BACHS_WEBHOOK_SECRET is not configured.")

        return webhooks.construct_event(raw_body, headers, secret)
