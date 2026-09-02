from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from django.db.models import Q
from django.utils.dateparse import parse_date

from content.models import ContentPost
from content.serializers import (
    ContentPostCreateSerializer,
    ContentPostResponseSerializer,
    ContentPostUpdateSerializer,
    PhotoPostCreateSerializer,
    PresignedUrlRequestSerializer,
    TextPostCreateSerializer,
)
from content.services.content_post_service import ContentPostService
from users.services.brand_service import BrandService
from utils.custom_logger import CustomLogger
from utils.r2_storage import R2StorageService
from utils.responses import CustomErrorResponse, CustomSuccessResponse


class ContentPostViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @swagger_auto_schema(
        operation_summary="Generate a presigned URL for media upload",
        operation_description=(
            "Returns a presigned URL that the frontend can use to upload media (video or photo) "
            "directly to R2. Also returns the 'key' which must be passed when creating the post."
        ),
        request_body=PresignedUrlRequestSerializer,
        responses={
            200: openapi.Response(
                "Success",
                openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "key": openapi.Schema(type=openapi.TYPE_STRING),
                            "url": openapi.Schema(type=openapi.TYPE_STRING),
                        },
                    ),
                ),
            ),
            400: openapi.Response("Bad Request"),
        },
    )
    @action(detail=False, methods=["post"], url_path="presigned-url")
    def get_presigned_url(self, request):
        """
        POST /api/content/posts/presigned-url/
        """
        serializer = PresignedUrlRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        files = serializer.validated_data["files"]

        results = []
        for file_req in files:
            result = R2StorageService.generate_presigned_upload_url(
                content_type=file_req["content_type"],
                extension=file_req.get("extension"),
            )
            if not result:
                return CustomErrorResponse(
                    "Failed to generate presigned URL.",
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            results.append(result)

        return CustomSuccessResponse(results)

    # ── Video ──────────────────────────────────────────────

    @swagger_auto_schema(
        operation_summary="Create and publish a video post to multiple platforms",
        operation_description=(
            "Uploads a video file, stores it temporarily in R2, creates a ContentPost "
            "with per-platform sub-entries, and dispatches async Celery tasks to publish "
            "the video to each selected platform. Each platform must already be connected "
            "to the user's active brand."
        ),
        request_body=ContentPostCreateSerializer,
        responses={
            201: ContentPostResponseSerializer,
            400: openapi.Response("Bad Request"),
        },
    )
    @action(detail=False, methods=["post"], url_path="video")
    def create_video(self, request):
        """
        POST /api/content/posts/video/
        """
        serializer = ContentPostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        return self._create_and_dispatch(
            request=request,
            media_keys=[validated["video_key"]],
            caption=validated.get("caption", ""),
            platforms=validated["platforms"],
            platform_settings=validated.get("platform_settings", {}),
            content_type="video",
            scheduled_at=validated.get("scheduled_at"),
            thumbnail_key=validated.get("thumbnail_key"),
            video_thumbnail_offset=validated.get("video_thumbnail_offset"),
        )

    # ── Photo ──────────────────────────────────────────────

    @swagger_auto_schema(
        operation_summary="Create and publish a photo post to multiple platforms",
        operation_description=(
            "Uploads one or more photo files, stores them temporarily in R2, creates "
            "a ContentPost with per-platform sub-entries, and dispatches async Celery "
            "tasks to publish the photos to each selected platform. Each platform must "
            "already be connected to the user's active brand."
        ),
        request_body=PhotoPostCreateSerializer,
        responses={
            201: ContentPostResponseSerializer,
            400: openapi.Response("Bad Request"),
        },
    )
    @action(detail=False, methods=["post"], url_path="photo")
    def create_photo(self, request):
        """
        POST /api/content/posts/photo/
        """
        serializer = PhotoPostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        return self._create_and_dispatch(
            request=request,
            media_keys=validated["photo_keys"],
            caption=validated.get("caption", ""),
            platforms=validated["platforms"],
            platform_settings=validated.get("platform_settings", {}),
            content_type="photo",
            scheduled_at=validated.get("scheduled_at"),
        )

    # ── Text ───────────────────────────────────────────────

    @swagger_auto_schema(
        operation_summary="Create and publish a text post to multiple platforms",
        operation_description=(
            "Creates a ContentPost with per-platform sub-entries, "
            "and dispatches async Celery tasks to publish the text "
            "to each selected platform (e.g. Facebook, LinkedIn). "
            "Each platform must already be connected to the user's active brand."
        ),
        request_body=TextPostCreateSerializer,
        responses={
            201: ContentPostResponseSerializer,
            400: openapi.Response("Bad Request"),
        },
    )
    @action(detail=False, methods=["post"], url_path="text")
    def create_text(self, request):
        """
        POST /api/content/posts/text/
        """
        serializer = TextPostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        return self._create_and_dispatch(
            request=request,
            media_keys=[],
            caption=validated["caption"],
            platforms=validated["platforms"],
            platform_settings=validated.get("platform_settings", {}),
            content_type="text",
            scheduled_at=validated.get("scheduled_at"),
        )

    # ── Calendar ───────────────────────────────────────────

    @swagger_auto_schema(
        operation_summary="Get calendar posts within a date range",
        operation_description=(
            "Returns a list of posts for the active brand that are either scheduled or created "
            "within the specified start_date and end_date range."
        ),
        manual_parameters=[
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="YYYY-MM-DD format",
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="YYYY-MM-DD format",
            ),
        ],
        responses={
            200: ContentPostResponseSerializer(many=True),
        },
    )
    @action(detail=False, methods=["get"], url_path="calendar")
    def get_calendar_posts(self, request):
        """
        GET /api/content/posts/calendar/
        """
        user = request.user
        try:
            brand = BrandService.get_default_brand(user)
        except ValueError as e:
            return CustomErrorResponse(str(e), status=status.HTTP_400_BAD_REQUEST)

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        posts = ContentPost.objects.filter(brand=brand).prefetch_related(
            "platform_entries", "media_items"
        )

        if start_date_str:
            start_date = parse_date(start_date_str)
            if start_date:
                posts = posts.filter(
                    Q(scheduled_at__date__gte=start_date)
                    | Q(scheduled_at__isnull=True, created_at__date__gte=start_date)
                )

        if end_date_str:
            end_date = parse_date(end_date_str)
            if end_date:
                posts = posts.filter(
                    Q(scheduled_at__date__lte=end_date)
                    | Q(scheduled_at__isnull=True, created_at__date__lte=end_date)
                )

        posts = posts.order_by("scheduled_at", "created_at")
        serializer = ContentPostResponseSerializer(posts, many=True)
        return CustomSuccessResponse(serializer.data)

    # ── Retrieve status ────────────────────────────────────

    @swagger_auto_schema(
        operation_summary="Get a content post by ID",
        operation_description=(
            "Returns the full details of a ContentPost by ID, including its media, "
            "caption, and per-platform status details (pending, uploading, posted, "
            "or failed) with platform_post_id and error_message for each platform."
        ),
        responses={
            200: ContentPostResponseSerializer,
            404: openapi.Response("Not Found"),
        },
    )
    @action(detail=True, methods=["get"], url_path="")
    def retrieve(self, request, pk=None):
        """
        GET /api/content/posts/{id}/
        """
        try:
            content_post = ContentPostService.get_content_post(
                post_id=pk, user=request.user
            )
        except ContentPost.DoesNotExist:
            return CustomErrorResponse(
                "Content post not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        response_data = ContentPostResponseSerializer(content_post).data
        return CustomSuccessResponse(response_data)

    @swagger_auto_schema(
        operation_summary="Update a scheduled content post",
        operation_description=(
            "Updates the caption, scheduled_at, or platform_settings of a ContentPost. "
            "Only allowed if the post has not started processing yet (all platforms are PENDING or SCHEDULED)."
        ),
        request_body=ContentPostUpdateSerializer,
        responses={
            200: ContentPostResponseSerializer,
            400: openapi.Response("Bad Request"),
            404: openapi.Response("Not Found"),
        },
    )
    def partial_update(self, request, pk=None):
        """
        PATCH /api/content/posts/{id}/
        """
        try:
            content_post = ContentPostService.get_content_post(
                post_id=pk, user=request.user
            )
        except ContentPost.DoesNotExist:
            return CustomErrorResponse(
                "Content post not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ContentPostUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            content_post = ContentPostService.update_content_post(
                content_post=content_post,
                validated_data=serializer.validated_data,
            )
        except ValueError as e:
            return CustomErrorResponse(
                str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_data = ContentPostResponseSerializer(content_post).data
        return CustomSuccessResponse(response_data)

    @swagger_auto_schema(
        operation_summary="Delete a scheduled content post",
        operation_description=(
            "Deletes a scheduled ContentPost and its associated media. "
            "Only allowed if the post has not started processing yet (all platforms are PENDING or SCHEDULED)."
        ),
        responses={
            204: openapi.Response("No Content"),
            400: openapi.Response("Bad Request"),
            404: openapi.Response("Not Found"),
        },
    )
    def destroy(self, request, pk=None):
        """
        DELETE /api/content/posts/{id}/
        """
        try:
            content_post = ContentPostService.get_content_post(
                post_id=pk, user=request.user
            )
        except ContentPost.DoesNotExist:
            return CustomErrorResponse(
                "Content post not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            ContentPostService.delete_content_post(content_post)
        except ValueError as e:
            return CustomErrorResponse(
                str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            "Post deleted successfully.",
            status=status.HTTP_204_NO_CONTENT,
        )

    # ── shared helper ──────────────────────────────────────

    def _create_and_dispatch(
        self,
        *,
        request,
        media_keys,
        platforms,
        content_type,
        caption="",
        platform_settings=None,
        scheduled_at=None,
        thumbnail_key=None,
        video_thumbnail_offset=None,
    ):
        """
        Shared pipeline: call the service (which handles R2 + DB + Celery),
        return the serialized response.
        """
        try:
            content_post = ContentPostService.create_content_post(
                user=request.user,
                media_keys=media_keys,
                caption=caption,
                platforms=platforms,
                platform_settings=platform_settings,
                content_type=content_type,
                scheduled_at=scheduled_at,
                thumbnail_key=thumbnail_key,
                video_thumbnail_offset=video_thumbnail_offset,
            )
        except ValueError as e:
            CustomLogger.exception(
                "content.views",
                f"Validation error in _create_and_dispatch",
                extra={"error": str(e)},
            )
            return CustomErrorResponse(
                str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            CustomLogger.exception(
                "content.views",
                "Unexpected error in _create_and_dispatch",
                extra={"error": str(e)},
            )
            return CustomErrorResponse(
                "An unexpected error occurred. Please try again later.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = ContentPostResponseSerializer(content_post).data
        return CustomSuccessResponse(response_data, status=status.HTTP_201_CREATED)
