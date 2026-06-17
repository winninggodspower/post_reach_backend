from rest_framework import serializers

from users.models import Brand


__all__ = [
    "FacebookAuthCodeSerializer",
    "FacebookPagesRequestSerializer",
    "GoogleAuthCodeSerializer",
    "InstagramAuthCodeSerializer",
    "LinkedinAuthCodeSerializer",
    "TiktokAuthCodeSerializer",
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


class FacebookPagesRequestSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)


class FacebookAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True,
    )
    page_id = serializers.CharField(required=False, allow_blank=True, default="")


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


class TiktokAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True,
    )
