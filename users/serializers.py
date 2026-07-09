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


class ConnectedAccountSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=SocialPlatformChoices.choices)
    external_id = serializers.CharField()
    account_name = serializers.CharField()
    profile_picture_url = serializers.URLField(allow_null=True, required=False)
    connected_at = serializers.DateTimeField(source="created_at")


class BrandSerializer(serializers.ModelSerializer):
    connected_accounts = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "industry",
            "posting_frequency",
            "primary_platform",
            "team_size",
            "connected_accounts",
        ]
        read_only_fields = fields

    def get_connected_accounts(self, brand):
        accounts = brand.social_accounts.all()
        return [
            ConnectedAccountSerializer(account).data
            for account in sorted(accounts, key=lambda account: account.created_at)
        ]


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
