from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from content.serializers import (
    ContentPostCreateSerializer,
    ContentPostResponseSerializer,
    PhotoPostCreateSerializer,
)
from content.services.content_creation_service import ContentCreationService
from utils.responses import CustomErrorResponse, CustomSuccessResponse


class ContentPostViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

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
    @parser_classes([MultiPartParser, FormParser])
    def create_video(self, request):
        """
        POST /api/content/posts/video/
        """
        serializer = ContentPostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        text = validated["title"]
        if validated.get("description"):
            text = f"{validated['title']}\n{validated['description']}"

        return self._create_and_dispatch(
            request=request,
            media_file=validated["video"],
            text=text,
            platforms=validated["platforms"],
            content_type="video",
        )

    # ── Photo ──────────────────────────────────────────────

    @swagger_auto_schema(
        operation_summary="Create and publish a photo post to multiple platforms",
        operation_description=(
            "Uploads a photo file, stores it temporarily in R2, creates a ContentPost "
            "with per-platform sub-entries, and dispatches async Celery tasks to publish "
            "the photo to each selected platform. Each platform must already be connected "
            "to the user's active brand."
        ),
        request_body=PhotoPostCreateSerializer,
        responses={
            201: ContentPostResponseSerializer,
            400: openapi.Response("Bad Request"),
        },
        consumes=["multipart/form-data"],
    )
    @action(detail=False, methods=["post"], url_path="photo")
    @parser_classes([MultiPartParser, FormParser])
    def create_photo(self, request):
        """
        POST /api/content/posts/photo/
        """
        serializer = PhotoPostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        return self._create_and_dispatch(
            request=request,
            media_file=validated["photo"],
            text=validated.get("text", ""),
            platforms=validated["platforms"],
            content_type="photo",
        )

    # ── shared helper ──────────────────────────────────────

    def _create_and_dispatch(self, *, request, media_file, text, platforms, content_type):
        """
        Shared pipeline: call the service (which handles R2 + DB + Celery),
        return the serialized response.
        """
        try:
            content_post = ContentCreationService.create_content_post(
                user=request.user,
                media_file=media_file,
                text=text,
                platforms=platforms,
                content_type=content_type,
            )
        except ValueError as e:
            return CustomErrorResponse(
                str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return CustomErrorResponse(
                f"Failed to create post: {str(e)}",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = ContentPostResponseSerializer(content_post).data
        return CustomSuccessResponse(response_data, status=status.HTTP_201_CREATED)