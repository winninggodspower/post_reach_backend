from rest_framework import serializers

from content.models import ContentMedia, ContentPost, ContentPostPlatform
from social_accounts.enums import PlatformChoices


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
        choices=PlatformChoices.choices, required=True
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
    media_items = ContentMediaSerializer(many=True, read_only=True)

    class Meta:
        model = ContentPost
        fields = [
            "id",
            "title",
            "description",
            "content_type",
            "media_items",
            "platforms",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields