from rest_framework import serializers

from social_accounts.enums import PlatformChoices as SocialPlatformChoices
from social_accounts.models import Brand
from users.enums import IndustryChoices, PlatformChoices, TeamSizeChoices

from .models import User


class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "handle", "password"]


class UserSerializer(serializers.ModelSerializer):
    has_completed_onboarding = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "handle",
            "role",
            "has_completed_onboarding",
            "brand",
        ]
        read_only_fields = fields

    def get_has_completed_onboarding(self, user):
        default_brand = self._get_default_brand(user)
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

    def _get_default_brand(self, user):
        """Return the user's default brand, preferring prefetched data."""
        if (
            hasattr(user, "_prefetched_objects_cache")
            and "brands" in user._prefetched_objects_cache
        ):
            brands = user._prefetched_objects_cache["brands"]
            return next((b for b in brands if b.is_default), None)
        return user.brands.filter(is_default=True).first()

    def get_brand(self, user):
        default_brand = self._get_default_brand(user)
        if default_brand is None:
            return None
        return BrandSerializer(default_brand).data


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "handle"]
        extra_kwargs = {
            "first_name": {"required": False},
            "last_name": {"required": False},
            "handle": {"required": False, "allow_null": True, "allow_blank": True},
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
    redirect_uri = serializers.CharField(required=True)


class OnboardingSerializer(serializers.Serializer):
    industry = serializers.ChoiceField(choices=IndustryChoices.choices)
    posting_frequency = serializers.CharField(max_length=100)
    primary_platform = serializers.ChoiceField(choices=PlatformChoices.choices)
    role = serializers.ChoiceField(choices=User.RoleChoices.choices)
    team_size = serializers.ChoiceField(choices=TeamSizeChoices.choices)


class BrandSerializer(serializers.ModelSerializer):
    is_youtube_connected = serializers.SerializerMethodField()
    is_instagram_connected = serializers.SerializerMethodField()
    is_tiktok_connected = serializers.SerializerMethodField()
    is_facebook_connected = serializers.SerializerMethodField()
    is_linkedin_connected = serializers.SerializerMethodField()
    is_x_connected = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "industry",
            "posting_frequency",
            "primary_platform",
            "team_size",
            "is_youtube_connected",
            "is_instagram_connected",
            "is_tiktok_connected",
            "is_facebook_connected",
            "is_linkedin_connected",
            "is_x_connected",
        ]
        read_only_fields = fields

    def _platform_connected(self, brand, platform):
        return any(sa.platform == platform for sa in brand.social_accounts.all())

    def get_is_youtube_connected(self, brand):
        return self._platform_connected(brand, SocialPlatformChoices.YOUTUBE)

    def get_is_instagram_connected(self, brand):
        return self._platform_connected(brand, SocialPlatformChoices.INSTAGRAM)

    def get_is_tiktok_connected(self, brand):
        return self._platform_connected(brand, SocialPlatformChoices.TIKTOK)

    def get_is_facebook_connected(self, brand):
        return self._platform_connected(brand, SocialPlatformChoices.FACEBOOK)

    def get_is_linkedin_connected(self, brand):
        return self._platform_connected(brand, SocialPlatformChoices.LINKEDIN)

    def get_is_x_connected(self, brand):
        return self._platform_connected(brand, SocialPlatformChoices.TWITTER)


class OnboardingResponseDataSerializer(serializers.Serializer):
    user = UserSerializer()


class OnboardingResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = OnboardingResponseDataSerializer()


class RequestResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class VerifyResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, min_length=6, max_length=6)


class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8, write_only=True)


class VerifyOTPResponseDataSerializer(serializers.Serializer):
    reset_token = serializers.CharField()


class VerifyOTPResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = VerifyOTPResponseDataSerializer()
