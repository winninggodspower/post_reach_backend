from rest_framework import serializers


__all__ = [
    "ConnectAccountResponseSerializer",
    "FacebookPagesListResponseSerializer",
    "FacebookPagesResponseSerializer",
    "YoutubeAuthUrlResponseSerializer",
    "FacebookAuthUrlResponseSerializer",
    "InstagramAuthUrlResponseSerializer",
    "TiktokAuthUrlResponseSerializer",
    "LinkedinAuthUrlResponseSerializer",
]


class FacebookPagesResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    picture_url = serializers.URLField(allow_null=True)


class FacebookPagesListResponseSerializer(serializers.Serializer):
    pages = FacebookPagesResponseSerializer(many=True)



class YoutubeAuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField(help_text="The Google OAuth authorization URL")


class FacebookAuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField(help_text="The Facebook OAuth authorization URL")


class InstagramAuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField(help_text="The Instagram OAuth authorization URL")


class TiktokAuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField(help_text="The TikTok OAuth authorization URL")


class LinkedinAuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField(help_text="The LinkedIn OAuth authorization URL")


class ConnectAccountResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    platform = serializers.CharField()
    is_connected = serializers.BooleanField()


