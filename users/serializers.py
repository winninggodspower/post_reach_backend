from rest_framework import serializers

from users.enums import IndustryChoices, PlatformChoices, TeamSizeChoices

from .models import User
from social_accounts.models import Brand


class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'handle', 'password']


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    has_completed_onboarding = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'handle', 'role', 'has_completed_onboarding']
        read_only_fields = fields

    def get_has_completed_onboarding(self, user):
        default_brand = user.brands.filter(is_default=True).first()
        if not default_brand:
            return False

        required_values = [
            user.role,
            default_brand.industry,
            default_brand.posting_frequency,
            default_brand.primary_platform,
            default_brand.team_size,
        ]
        return all(required_values)


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


class OnboardingSerializer(serializers.Serializer):
    industry = serializers.ChoiceField(choices=IndustryChoices.choices)
    posting_frequency = serializers.CharField(max_length=100)
    primary_platform = serializers.ChoiceField(choices=PlatformChoices.choices)
    role = serializers.ChoiceField(choices=User.RoleChoices.choices)
    team_size = serializers.ChoiceField(choices=TeamSizeChoices.choices)


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = [
            'id',
            'name',
            'is_default',
            'industry',
            'posting_frequency',
            'primary_platform',
            'team_size',
        ]
        read_only_fields = fields


class OnboardingResponseDataSerializer(serializers.Serializer):
    user = UserSerializer()
    brand = BrandSerializer()


class OnboardingResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = OnboardingResponseDataSerializer()
