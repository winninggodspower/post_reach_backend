import json

from drf_yasg import openapi
from rest_framework import serializers

from content.enums import PhotoPlatformOptions, PostStatus, TextPlatformOptions
from content.models import ContentMedia, ContentPost, ContentPostPlatform
from social_accounts.enums import PlatformChoices
from utils.r2_storage import R2StorageService

# Used by the swagger_auto_schema in views.py for the platforms enum dropdown
PLATFORM_ENUMS = [choice[0] for choice in PlatformChoices.choices]
PHOTO_PLATFORM_ENUMS = [choice[0] for choice in PhotoPlatformOptions.choices]
TEXT_PLATFORM_ENUMS = [choice[0] for choice in TextPlatformOptions.choices]

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
        "caption",
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
    openapi.Parameter(
        "platform_settings",
        openapi.IN_FORM,
        type=openapi.TYPE_OBJECT,
        required=False,
        description="Platform-specific settings and overrides.",
    ),
    openapi.Parameter(
        "scheduled_at",
        openapi.IN_FORM,
        type=openapi.TYPE_STRING,
        format=openapi.FORMAT_DATETIME,
        required=False,
        description="Optional ISO 8601 datetime for post scheduling.",
    ),
]

# Swagger manual parameters for the text post endpoint
text_post_parameters = [
    openapi.Parameter(
        "caption",
        openapi.IN_FORM,
        type=openapi.TYPE_STRING,
        required=True,
        description="Caption text for the text post.",
    ),
    openapi.Parameter(
        "platforms",
        openapi.IN_FORM,
        type=openapi.TYPE_ARRAY,
        items=openapi.Items(type=openapi.TYPE_STRING, enum=TEXT_PLATFORM_ENUMS),
        required=True,
        description="Target platforms to publish to (must support text-only posts).",
    ),
    openapi.Parameter(
        "platform_settings",
        openapi.IN_FORM,
        type=openapi.TYPE_OBJECT,
        required=False,
        description="Platform-specific settings and overrides.",
    ),
    openapi.Parameter(
        "scheduled_at",
        openapi.IN_FORM,
        type=openapi.TYPE_STRING,
        format=openapi.FORMAT_DATETIME,
        required=False,
        description="Optional ISO 8601 datetime for post scheduling.",
    ),
]


class ContentPostCreateSerializer(serializers.Serializer):
    video = serializers.FileField(required=True)
    thumbnail = serializers.FileField(required=False, allow_null=True, default=None)
    video_thumbnail_offset = serializers.IntegerField(
        required=False, allow_null=True, default=None
    )
    caption = serializers.CharField(required=False, allow_blank=True, default="")
    scheduled_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None
    )
    platforms = serializers.MultipleChoiceField(
        choices=PlatformChoices.choices, required=True
    )
    platform_settings = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        platforms = attrs.get("platforms", set())
        platform_settings = attrs.get("platform_settings", {})

        # If youtube is selected, we require a YouTube title
        if "youtube" in platforms:
            yt_settings = platform_settings.get("youtube", {})
            if not yt_settings or not yt_settings.get("title"):
                raise serializers.ValidationError(
                    {
                        "platform_settings": "YouTube requires a title in platform_settings.youtube.title"
                    }
                )
        return attrs


class ContentPostPlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentPostPlatform
        fields = [
            "id",
            "platform",
            "status",
            "platform_post_id",
            "post_url",
            "error_message",
            "title",
            "caption",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PhotoPostCreateSerializer(serializers.Serializer):
    photos = serializers.ListField(
        child=serializers.FileField(), required=True, min_length=1
    )
    caption = serializers.CharField(required=False, allow_blank=True, default="")
    scheduled_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None
    )
    platforms = serializers.MultipleChoiceField(
        choices=PhotoPlatformOptions.choices, required=True
    )
    platform_settings = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        platforms = attrs.get("platforms", set())
        platform_settings = attrs.get("platform_settings", {})

        if "youtube" in platforms:
            yt_settings = platform_settings.get("youtube", {})
            if not yt_settings or not yt_settings.get("title"):
                raise serializers.ValidationError(
                    {
                        "platform_settings": "YouTube requires a title in platform_settings.youtube.title"
                    }
                )
        return attrs


class TextPostCreateSerializer(serializers.Serializer):
    caption = serializers.CharField(required=True, allow_blank=False)
    scheduled_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None
    )
    platforms = serializers.MultipleChoiceField(
        choices=TextPlatformOptions.choices, required=True
    )
    platform_settings = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        # Validation is handled by TextPlatformOptions choices in platforms MultipleChoiceField
        return attrs


class ContentPostUpdateSerializer(serializers.Serializer):
    caption = serializers.CharField(required=False, allow_blank=True)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    platform_settings = serializers.JSONField(required=False)
    platforms = serializers.MultipleChoiceField(
        choices=PlatformChoices.choices, required=False
    )

    def validate_platform_settings(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Must be a valid JSON object.")
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be a dictionary/JSON object.")
        return value

    def validate(self, attrs):
        # We can add platform-specific validation here if needed
        return attrs


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
    thumbnail_url = serializers.SerializerMethodField()
    media_urls = serializers.SerializerMethodField()

    class Meta:
        model = ContentPost
        fields = [
            "id",
            "caption",
            "content_type",
            "scheduled_at",
            "platforms",
            "thumbnail_url",
            "video_thumbnail_offset",
            "media_urls",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _is_media_deleted(self, obj):
        # Since platform_entries are prefetched, we iterate in memory to avoid N+1 queries
        for entry in obj.platform_entries.all():
            if entry.status not in [PostStatus.POSTED, PostStatus.FAILED]:
                return False
        return True

    def get_thumbnail_url(self, obj):
        if self._is_media_deleted(obj):
            return None
        if obj.thumbnail_r2_key:
            return R2StorageService.generate_presigned_url(obj.thumbnail_r2_key)
        return None

    def get_media_urls(self, obj):
        if self._is_media_deleted(obj):
            return []
        urls = []
        for media in obj.media_items.all():
            url = R2StorageService.generate_presigned_url(media.r2_key)
            if url:
                urls.append(url)
        return urls
