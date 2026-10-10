from drf_yasg.utils import swagger_serializer_method
from rest_framework import serializers

from social_accounts.enums import PlatformChoices as SocialPlatformChoices
from social_accounts.models import Brand
from users.enums import IndustryChoices, PlatformChoices, TeamSizeChoices
from users.services.brand_service import BrandService
from users.services.user_service import UserService

from .models import User


class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "handle", "password"]


class ConnectedAccountSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=SocialPlatformChoices.choices)
    external_id = serializers.CharField()
    account_name = serializers.CharField()
    profile_picture_url = serializers.URLField(allow_null=True, required=False)
    connected_at = serializers.DateTimeField(source="last_connected_at")
    is_expired = serializers.SerializerMethodField()
    expired_at = serializers.DateTimeField(source="token_expires_at", allow_null=True)
    is_premium = serializers.SerializerMethodField()

    @swagger_serializer_method(serializer_or_field=serializers.BooleanField())
    def get_is_expired(self, obj):
        return obj.get_access_token() is None

    @swagger_serializer_method(serializer_or_field=serializers.BooleanField())
    def get_is_premium(self, obj):
        return bool(obj.metadata.get("is_premium", False))


class BrandSerializer(serializers.ModelSerializer):
    connected_accounts = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "logo_url",
            "industry",
            "posting_frequency",
            "primary_platform",
            "team_size",
            "connected_accounts",
        ]
        read_only_fields = ["id", "logo_url", "connected_accounts"]

    @swagger_serializer_method(
        serializer_or_field=ConnectedAccountSerializer(many=True)
    )
    def get_connected_accounts(self, brand):
        accounts = brand.social_accounts.all()
        return [
            ConnectedAccountSerializer(account).data
            for account in sorted(
                accounts, key=lambda account: account.last_connected_at
            )
        ]


class BrandBriefSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "logo_url",
            "is_default",
            "is_active",
            "role",
        ]
        read_only_fields = fields

    @swagger_serializer_method(serializer_or_field=serializers.BooleanField())
    def get_is_active(self, brand):
        active_brand_id = self.context.get("active_brand_id")
        return bool(active_brand_id and brand.id == active_brand_id)

    @swagger_serializer_method(serializer_or_field=serializers.CharField())
    def get_role(self, brand):
        user = self.context.get("user")
        if user and brand.user_id == user.id:
            return "owner"
        return "collaborator"


class UserSerializer(serializers.ModelSerializer):
    has_completed_onboarding = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    brands = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "handle",
            "profile_picture_url",
            "role",
            "has_completed_onboarding",
            "brand",
            "brands",
        ]
        read_only_fields = fields

    @swagger_serializer_method(serializer_or_field=serializers.BooleanField())
    def get_has_completed_onboarding(self, user):
        active_brand = UserService.get_active_brand(user)
        if not active_brand:
            return False

        required_values = [
            user.role,
            active_brand.industry,
            active_brand.posting_frequency,
            active_brand.primary_platform,
            active_brand.team_size,
        ]
        return all(required_values)

    @swagger_serializer_method(serializer_or_field=BrandSerializer)
    def get_brand(self, user):
        active_brand = UserService.get_active_brand(user)
        return BrandSerializer(active_brand).data

    @swagger_serializer_method(serializer_or_field=BrandBriefSerializer(many=True))
    def get_brands(self, user):
        active_brand = UserService.get_active_brand(user)
        active_brand_id = active_brand.id if active_brand else None
        accessible_brands = BrandService.get_accessible_brands(user)
        return BrandBriefSerializer(
            accessible_brands,
            many=True,
            context={"active_brand_id": active_brand_id, "user": user},
        ).data


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


class SetActiveBrandSerializer(serializers.Serializer):
    brand_id = serializers.UUIDField(required=True)
