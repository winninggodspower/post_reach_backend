from drf_yasg.utils import swagger_auto_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from analytics.permissions import IsSuperAdminUser
from analytics.serializers import (
    AdminAnalyticsResponseSerializer,
    AdminAnalyticsSummaryResponseSerializer,
)
from analytics.services import AdminAnalyticsService
from utils.responses import CustomSuccessResponse


class AdminAnalyticsSummaryView(APIView):
    """
    Superadmin endpoint that returns the concise executive summary (headline KPIs).
    """

    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    @swagger_auto_schema(
        operation_summary="Get admin analytics summary",
        operation_description=(
            "Returns top-level executive KPIs (total users, onboarding completion, "
            "connected accounts, and live posts count). Requires superadmin privileges."
        ),
        responses={
            200: AdminAnalyticsSummaryResponseSerializer,
            401: "Authentication credentials were not provided or are invalid.",
            403: "Permission denied. Superadmin privileges required.",
        },
    )
    def get(self, request):
        data = AdminAnalyticsService.get_executive_summary()
        return CustomSuccessResponse(
            data=data,
            message="Admin analytics summary retrieved successfully.",
        )


class AdminAnalyticsOverviewView(APIView):
    """
    Superadmin endpoint that returns aggregated platform telemetry and operational analytics.
    """

    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    @swagger_auto_schema(
        operation_summary="Get admin analytics overview",
        operation_description=(
            "Returns aggregated platform-wide telemetry, user growth, onboarding metrics, "
            "brand connection rates, post publishing status, and storage indicators. "
            "Requires superadmin privileges."
        ),
        responses={
            200: AdminAnalyticsResponseSerializer,
            401: "Authentication credentials were not provided or are invalid.",
            403: "Permission denied. Superadmin privileges required.",
        },
    )
    def get(self, request):
        data = AdminAnalyticsService.get_platform_overview()
        return CustomSuccessResponse(
            data=data,
            message="Admin analytics retrieved successfully.",
        )
