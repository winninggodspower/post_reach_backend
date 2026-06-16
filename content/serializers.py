from rest_framework import serializers

from content.models import ContentPost, ContentPostPlatform
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
    photo = serializers.FileField(required=True)
    text = serializers.CharField(required=False, allow_blank=True, default="")
    platforms = serializers.MultipleChoiceField(
        choices=PlatformChoices.choices, required=True
    )


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
