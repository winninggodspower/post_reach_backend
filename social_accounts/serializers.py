from rest_framework import serializers

from social_accounts.models import SocialAccount
from users.models import Brand


class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = [
            "user",
            "platform",
            "expires_at",
            "token_type",
        ]
        # make all fields read only
        read_only_fields = [
            "user",
            "platform",
            "expires_at",
            "token_type",
        ]

class GoogleAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
    )

class FacebookAuthCodeSerializer(serializers.Serializer):
    short_lived_access_token = serializers.CharField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
    )

class InstagramAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
    )

class LinkedinAuthCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
    )
