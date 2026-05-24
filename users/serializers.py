from rest_framework import serializers

from .models import User


class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'handle', 'password']


class SignInSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)


class AuthTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()


class GoogleAuthSerializer(serializers.Serializer):
    auth_code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
