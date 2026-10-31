from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from oauth2_provider.contrib.rest_framework import (
    OAuth2ProtectedResourceAuthentication,
    TokenHasScope,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from content.models import ContentPost
from content.selectors import ContentPostSelector
from content.serializers import (
    ContentPostResponseSerializer,
    ContentPostUpdateSerializer,
    TextPostCreateSerializer,
)
from content.services.content_post_service import ContentPostService
from users.serializers import BrandBriefSerializer, ConnectedAccountSerializer
from users.services.brand_service import BrandService
from users.services.user_service import UserService
from utils.responses import CustomErrorResponse, CustomSuccessResponse


def _resolve_target_brand(user, brand_id=None):
    if brand_id:
        try:
            return BrandService.get_brand_by_id(user, brand_id)
        except Exception as exc:
            raise ValueError(
                f"Brand '{brand_id}' not found or not accessible."
            ) from exc

    active_brand = UserService.get_active_brand(user)
    if not active_brand:
        raise ValueError(
            "No active brand found. Please select an active brand or specify brand_id."
        )
    return active_brand


class BrandListView(APIView):
    """List accessible PostGlee brands for the authenticated developer token."""

    authentication_classes = [OAuth2ProtectedResourceAuthentication]
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ["accounts:read"]

    @swagger_auto_schema(
        operation_summary="List brands (v1)",
        operation_description="Returns all brands accessible to the authenticated OAuth token (requires 'accounts:read' scope).",
        responses={200: BrandBriefSerializer(many=True)},
    )
    def get(self, request):
        active_brand = UserService.get_active_brand(request.user)
        active_brand_id = active_brand.id if active_brand else None
        brands = BrandService.get_accessible_brands(request.user)
        serializer = BrandBriefSerializer(
            brands,
            many=True,
            context={"active_brand_id": active_brand_id, "user": request.user},
        )
        return CustomSuccessResponse(
            data=serializer.data, message="Brands retrieved successfully."
        )


class AccountListView(APIView):
    """List connected social media accounts for a brand."""

    authentication_classes = [OAuth2ProtectedResourceAuthentication]
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ["accounts:read"]

    @swagger_auto_schema(
        operation_summary="List connected social accounts (v1)",
        operation_description="Returns connected social accounts for a brand (requires 'accounts:read' scope).",
        manual_parameters=[
            openapi.Parameter(
                "brand_id",
                openapi.IN_QUERY,
                description="Optional UUID of the brand. Defaults to user's active brand.",
                type=openapi.TYPE_STRING,
            )
        ],
        responses={200: ConnectedAccountSerializer(many=True)},
    )
    def get(self, request):
        brand_id = request.query_params.get("brand_id")
        try:
            brand = _resolve_target_brand(request.user, brand_id)
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_404_NOT_FOUND
            )

        accounts = sorted(
            brand.social_accounts.all(), key=lambda acc: acc.last_connected_at
        )
        serializer = ConnectedAccountSerializer(accounts, many=True)
        return CustomSuccessResponse(
            data={
                "brand_id": str(brand.id),
                "brand_name": brand.name,
                "connected_accounts": serializer.data,
            },
            message="Connected accounts retrieved successfully.",
        )


class PostListCreateView(APIView):
    """List scheduled posts or create/schedule a new social post."""

    authentication_classes = [OAuth2ProtectedResourceAuthentication]
    permission_classes = [IsAuthenticated, TokenHasScope]

    @property
    def required_scopes(self):
        if self.request.method == "POST":
            return ["posts:write"]
        return ["posts:read"]

    @swagger_auto_schema(
        operation_summary="List upcoming scheduled posts (v1)",
        operation_description="Returns upcoming scheduled posts for a brand (requires 'posts:read' scope).",
        manual_parameters=[
            openapi.Parameter("brand_id", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("platform", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter(
                "content_type", openapi.IN_QUERY, type=openapi.TYPE_STRING
            ),
            openapi.Parameter("limit", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
        ],
        responses={200: ContentPostResponseSerializer(many=True)},
    )
    def get(self, request):
        brand_id = request.query_params.get("brand_id")
        platform = request.query_params.get("platform")
        content_type = request.query_params.get("content_type")
        limit = request.query_params.get("limit")

        try:
            brand = _resolve_target_brand(request.user, brand_id)
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_404_NOT_FOUND
            )

        parsed_limit = int(limit) if limit and limit.isdigit() else None
        posts = ContentPostSelector.get_scheduled_posts(
            brand=brand,
            platform=platform,
            content_type=content_type,
            limit=parsed_limit,
        )
        serializer = ContentPostResponseSerializer(posts, many=True)
        return CustomSuccessResponse(data=serializer.data)

    @swagger_auto_schema(
        operation_summary="Create or schedule a social post (v1)",
        operation_description="Publishes a post immediately or schedules it if 'scheduled_at' is provided (requires 'posts:write' scope).",
        request_body=TextPostCreateSerializer,
        responses={201: ContentPostResponseSerializer},
    )
    def post(self, request):
        serializer = TextPostCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        brand_id = request.data.get("brand_id")
        try:
            brand = _resolve_target_brand(request.user, brand_id)
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_404_NOT_FOUND
            )

        try:
            post = ContentPostService.create_content_post(
                user=request.user,
                brand=brand,
                media_keys=[],
                caption=data["caption"],
                platforms=list(data["platforms"]),
                platform_settings=data.get("platform_settings", {}),
                content_type="text",
                scheduled_at=data.get("scheduled_at"),
            )
        except Exception as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_400_BAD_REQUEST
            )

        response_serializer = ContentPostResponseSerializer(post)
        status_msg = (
            "Post scheduled successfully."
            if data.get("scheduled_at")
            else "Post created and queued for publishing."
        )
        return CustomSuccessResponse(
            data=response_serializer.data,
            message=status_msg,
            status=status.HTTP_201_CREATED,
        )


class PostCalendarView(APIView):
    """Retrieve calendar posts within a date range."""

    authentication_classes = [OAuth2ProtectedResourceAuthentication]
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ["posts:read"]

    @swagger_auto_schema(
        operation_summary="Get calendar posts (v1)",
        operation_description="Returns scheduled and published posts within a date range (requires 'posts:read' scope).",
        manual_parameters=[
            openapi.Parameter("brand_id", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="YYYY-MM-DD",
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="YYYY-MM-DD",
            ),
        ],
        responses={200: ContentPostResponseSerializer(many=True)},
    )
    def get(self, request):
        brand_id = request.query_params.get("brand_id")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        try:
            brand = _resolve_target_brand(request.user, brand_id)
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_404_NOT_FOUND
            )

        try:
            start_date, end_date = ContentPostSelector.resolve_calendar_date_range(
                start_date, end_date
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_400_BAD_REQUEST
            )

        posts = ContentPostSelector.get_calendar_posts(
            brand=brand,
            start_date=start_date,
            end_date=end_date,
        )
        serializer = ContentPostResponseSerializer(posts, many=True)
        return CustomSuccessResponse(data=serializer.data)


class PostDetailView(APIView):
    """Retrieve, update/reschedule, or delete a social post."""

    authentication_classes = [OAuth2ProtectedResourceAuthentication]
    permission_classes = [IsAuthenticated, TokenHasScope]

    @property
    def required_scopes(self):
        if self.request.method in ["PATCH", "DELETE"]:
            return ["posts:write"]
        return ["posts:read"]

    @swagger_auto_schema(
        operation_summary="Get post details (v1)",
        operation_description="Returns full post details and per-platform status (requires 'posts:read' scope).",
        responses={200: ContentPostResponseSerializer, 404: "Post not found"},
    )
    def get(self, request, post_id: str):
        try:
            post = ContentPostSelector.get_content_post(
                post_id=post_id, user=request.user
            )
        except ContentPost.DoesNotExist:
            return CustomErrorResponse(
                message="Content post not found.", status=status.HTTP_404_NOT_FOUND
            )

        serializer = ContentPostResponseSerializer(post)
        return CustomSuccessResponse(data=serializer.data)

    @swagger_auto_schema(
        operation_summary="Update or reschedule a post (v1)",
        operation_description="Updates caption, scheduled_at, or platforms of a pending post (requires 'posts:write' scope).",
        request_body=ContentPostUpdateSerializer,
        responses={200: ContentPostResponseSerializer, 404: "Post not found"},
    )
    def patch(self, request, post_id: str):
        try:
            post = ContentPostSelector.get_content_post(
                post_id=post_id, user=request.user
            )
        except ContentPost.DoesNotExist:
            return CustomErrorResponse(
                message="Content post not found.", status=status.HTTP_404_NOT_FOUND
            )

        serializer = ContentPostUpdateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated = ContentPostService.update_content_post(
                content_post=post, validated_data=data
            )
        except Exception as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_400_BAD_REQUEST
            )

        response_serializer = ContentPostResponseSerializer(updated)
        return CustomSuccessResponse(
            data=response_serializer.data, message="Post updated successfully."
        )

    @swagger_auto_schema(
        operation_summary="Delete / cancel a post (v1)",
        operation_description="Deletes a pending or scheduled post (requires 'posts:write' scope).",
        responses={200: "Post deleted successfully", 404: "Post not found"},
    )
    def delete(self, request, post_id: str):
        try:
            post = ContentPostSelector.get_content_post(
                post_id=post_id, user=request.user
            )
        except ContentPost.DoesNotExist:
            return CustomErrorResponse(
                message="Content post not found.", status=status.HTTP_404_NOT_FOUND
            )

        try:
            ContentPostService.delete_content_post(post)
        except Exception as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_400_BAD_REQUEST
            )

        return CustomSuccessResponse(message="Post deleted successfully.")
