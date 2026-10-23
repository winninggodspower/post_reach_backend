import logging
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from subscriptions.serializers import (
    CancelSubscriptionRequestSerializer,
    CheckoutSessionRequestSerializer,
    CheckoutSessionResponseSerializer,
    CustomerPortalResponseSerializer,
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
)
from subscriptions.services import BachsService, SubscriptionService, WebhookService
from utils.responses import CustomErrorResponse, CustomSuccessResponse

logger = logging.getLogger(__name__)


class SubscriptionPlansView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="List subscription plans",
        operation_description="Returns all active subscription plans with pricing in USD and NGN, and plan features.",
        responses={
            200: SubscriptionPlanSerializer(many=True),
        },
    )
    def get(self, request):
        plans = SubscriptionService.get_all_plans()
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return CustomSuccessResponse(
            data=serializer.data,
            message="Subscription plans retrieved successfully.",
        )


class UserSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get current user subscription",
        operation_description="Returns the authenticated user's current subscription tier, active status, validity, and renewal dates.",
        responses={
            200: SubscriptionSerializer,
            401: "Authentication credentials were not provided or are invalid.",
        },
    )
    def get(self, request):
        sub = SubscriptionService.get_or_create_default_subscription(request.user)
        serializer = SubscriptionSerializer(sub)
        return CustomSuccessResponse(
            data=serializer.data,
            message="Subscription details retrieved successfully.",
        )


class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Create checkout session",
        operation_description=(
            "Creates a checkout session with Bachs for paid plans ('pro' or 'enterprise'). "
            "Supports card (USD) for recurring subscription or bank_transfer (NGN) for money transfer."
        ),
        request_body=CheckoutSessionRequestSerializer,
        responses={
            201: CheckoutSessionResponseSerializer,
            400: "Validation or processing error.",
            401: "Unauthorized.",
        },
    )
    def post(self, request):
        serializer = CheckoutSessionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        try:
            checkout_result = SubscriptionService.create_checkout_session(
                user=request.user,
                plan_tier=data["plan_tier"],
                currency=data.get("currency", "USD"),
                payment_method_type=data.get("payment_method", "auto"),
                success_url=data.get("success_url") or None,
                cancel_url=data.get("cancel_url") or None,
            )
            return CustomSuccessResponse(
                data=checkout_result,
                message="Checkout session created successfully.",
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Failed to create checkout session: {e}", exc_info=True)
            return CustomErrorResponse(
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )


class CustomerPortalView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get customer billing portal",
        operation_description="Returns a Bachs Customer Portal URL where users can manage their payment cards, view invoices, and manage subscriptions.",
        responses={
            200: CustomerPortalResponseSerializer,
            400: "No billing profile found for user.",
            401: "Unauthorized.",
        },
    )
    def post(self, request):
        try:
            portal_session = SubscriptionService.create_customer_portal_session(request.user)
            return CustomSuccessResponse(
                data={"portal_url": portal_session.get("url")},
                message="Customer portal session created successfully.",
            )
        except Exception as e:
            return CustomErrorResponse(
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )


class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Cancel active subscription",
        operation_description="Cancels the user's active paid subscription, optionally at period end.",
        request_body=CancelSubscriptionRequestSerializer,
        responses={
            200: SubscriptionSerializer,
            400: "Unable to cancel subscription.",
            401: "Unauthorized.",
        },
    )
    def post(self, request):
        serializer = CancelSubscriptionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cancel_at_period_end = serializer.validated_data.get("cancel_at_period_end", True)
        try:
            sub = SubscriptionService.cancel_user_subscription(
                user=request.user,
                cancel_at_period_end=cancel_at_period_end,
            )
            return CustomSuccessResponse(
                data=SubscriptionSerializer(sub).data,
                message="Subscription cancellation requested successfully.",
            )
        except Exception as e:
            return CustomErrorResponse(
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )


@method_decorator(csrf_exempt, name="dispatch")
class BachsWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @swagger_auto_schema(
        operation_summary="Bachs webhook endpoint",
        operation_description="Receives real-time payment notifications and subscription state changes from Bachs.",
        responses={
            200: "Event processed successfully.",
            400: "Invalid signature or malformed event payload.",
        },
    )
    def post(self, request):
        raw_body = request.body
        try:
            event = BachsService.verify_and_construct_webhook_event(
                raw_body=raw_body,
                headers=dict(request.headers),
            )
        except Exception as err:
            logger.warning(f"Bachs webhook verification failed: {err}")
            return HttpResponseBadRequest("Invalid signature")

        success, msg = WebhookService.process_webhook_event(event)
        if not success:
            logger.error(f"Error processing Bachs webhook event: {msg}")
            return HttpResponse(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return HttpResponse(status=status.HTTP_200_OK)
