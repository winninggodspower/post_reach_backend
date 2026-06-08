from rest_framework import serializers

from users.models import Brand


__all__ = [
    "FacebookAuthCodeSerializer",
    "GoogleAuthCodeSerializer",
    "InstagramAuthCodeSerializer",
    "LinkedinAuthCodeSerializer",
]


class GoogleAuthCodeSerializer(serializers.Serializer):

    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=False)
    state = serializers.CharField(required=False, allow_blank=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True,
    )


class FacebookAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True,
    )


class InstagramAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True,
    )


class LinkedinAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True,
    )
