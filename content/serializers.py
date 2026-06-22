from drf_yasg import openapi
from rest_framework import serializers

from content.enums import PhotoPlatformOptions
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from social_accounts.enums import PlatformChoices

# Used by the swagger_auto_schema in views.py for the platforms enum dropdown
PLATFORM_ENUMS = [choice[0] for choice in PlatformChoices.choices]
PHOTO_PLATFORM_ENUMS = [choice[0] for choice in PhotoPlatformOptions.choices]

# Swagger manual parameters for the photo post endpoint
photo_post_parameters = [
    openapi.Parameter(
        "photos",
        openapi.IN_FORM,
        type=openapi.TYPE_ARRAY,
        items=openapi.Items(type=openapi.TYPE_FILE),
        required=True,
        description="One or more photo files to upload.",
    ),
    openapi.Parameter(
        "text",
        openapi.IN_FORM,
        type=openapi.TYPE_STRING,
        required=False,
        description="Caption text for the photo post.",
    ),
    openapi.Parameter(
        "platforms",
        openapi.IN_FORM,
        type=openapi.TYPE_ARRAY,
        items=openapi.Items(type=openapi.TYPE_STRING, enum=PHOTO_PLATFORM_ENUMS),
        required=True,
        description="Target platforms to publish to (YouTube does not support photos).",
    ),
]


class ContentPostCreateSerializer(serializers.Serializer):
    video = serializers.FileField(required=True)
    title = serializers.CharField(required=True, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    platforms = serializers.MultipleChoiceField(
        choices=PlatformChoices.choices, required=True
    )


class ContentPostPlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentPostPlatform
        fields = [
            "id",
            "platform",
            "status",
            "platform_post_id",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PhotoPostCreateSerializer(serializers.Serializer):
    photos = serializers.ListField(
        child=serializers.FileField(), required=True, min_length=1
    )
    text = serializers.CharField(required=False, allow_blank=True, default="")
    platforms = serializers.MultipleChoiceField(
        choices=PhotoPlatformOptions.choices, required=True
    )


class ContentMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentMedia
        fields = [
            "id",
            "r2_key",
            "file_type",
            "order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ContentPostResponseSerializer(serializers.ModelSerializer):
    platforms = ContentPostPlatformSerializer(
        source="platform_entries", many=True, read_only=True
    )

    class Meta:
        model = ContentPost
        fields = [
            "id",
            "title",
            "description",
            "content_type",
            "platforms",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
