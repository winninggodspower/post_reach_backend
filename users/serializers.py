from rest_framework import serializers

from .models import User


class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'handle', 'password']


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'handle']
        read_only_fields = fields


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'handle']
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'handle': {'required': False, 'allow_null': True, 'allow_blank': True},
        }


class UserResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = UserSerializer()


class SignInSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)


class AuthTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()


class AuthDataSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = AuthTokenSerializer()


class AuthResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = AuthDataSerializer()


class GoogleAuthSerializer(serializers.Serializer):
    auth_code = serializers.CharField(required=True)
    redirect_uri = serializers.URLField(required=True)
