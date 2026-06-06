from rest_framework import serializers


__all__ = [
    "ConnectAccountResponseSerializer",
    "YoutubeAuthUrlResponseSerializer",
]


class YoutubeAuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField(help_text="The Google OAuth authorization URL")


class ConnectAccountResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    platform = serializers.CharField()
    is_connected = serializers.BooleanField()


