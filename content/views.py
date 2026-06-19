from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from content.models import ContentPost
from content.serializers import (
    ContentPostCreateSerializer,
    ContentPostResponseSerializer,
    PhotoPostCreateSerializer,
    photo_post_parameters,
)
from content.services.content_creation_service import ContentCreationService
from content.services.content_post_service import ContentPostService
from utils.custom_logger import CustomLogger
from utils.responses import CustomErrorResponse, CustomSuccessResponse


class ContentPostViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

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
        consumes=["multipart/form-data"],
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
            media_files=[validated["video"]],
            title=validated["title"],
            description=validated.get("description", ""),
            platforms=validated["platforms"],
            content_type="video",
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
        manual_parameters=photo_post_parameters,
        responses={
            201: ContentPostResponseSerializer,
            400: openapi.Response("Bad Request"),
        },
        consumes=["multipart/form-data"],
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
            media_files=validated["photos"],
            title=validated.get("text", ""),
            platforms=validated["platforms"],
            content_type="photo",
        )

    # ── Retrieve status ────────────────────────────────────

    @swagger_auto_schema(
        operation_summary="Get the status of a content post",
        operation_description=(
            "Returns a ContentPost by ID with per-platform status details "
            "(pending, uploading, posted, or failed) including platform_post_id "
            "and error_message for each platform."
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

    # ── shared helper ──────────────────────────────────────

    def _create_and_dispatch(self, *, request, media_files, platforms, content_type, title, description=""):
        """
        Shared pipeline: call the service (which handles R2 + DB + Celery),
        return the serialized response.
        """
        try:
            content_post = ContentCreationService.create_content_post(
                user=request.user,
                media_files=media_files,
                title=title,
                description=description,
                platforms=platforms,
                content_type=content_type,
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