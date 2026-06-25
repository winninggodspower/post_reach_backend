from django.db.models import Prefetch
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from integrations.services.google_auth_service import GoogleAuthService
from users.models import Brand, User
from users.services import OnboardingService, PasswordResetService, UserService
from utils.responses import CustomErrorResponse, CustomSuccessResponse

from .serializers import (
    AuthResponseSerializer,
    GoogleAuthSerializer,
    OnboardingResponseSerializer,
    OnboardingSerializer,
    RegisterUserSerializer,
    RequestResetOTPSerializer,
    ResetPasswordSerializer,
    SignInSerializer,
    UserResponseSerializer,
    UserSerializer,
    UserUpdateSerializer,
    VerifyOTPResponseSerializer,
    VerifyResetOTPSerializer,
)


# Create your views here.
def _prefetch_user_for_serialization(user):
    """Prefetch brands and their social_accounts to avoid N+1 queries."""
    return User.objects.prefetch_related(
        Prefetch("brands", queryset=Brand.objects.prefetch_related("social_accounts"))
    ).get(pk=user.pk)


def get_auth_response_data(user):
    return {
        "user": UserSerializer(_prefetch_user_for_serialization(user)).data,
        "tokens": UserService.get_auth_tokens(user),
    }


def get_onboarding_response_data(user, brand):
    # UserSerializer now includes `brand` nested inside, so we only need the user.
    return {
        "user": UserSerializer(_prefetch_user_for_serialization(user)).data,
    }


class RegisterUserView(APIView):
    serializer_class = RegisterUserSerializer

    @swagger_auto_schema(
        operation_summary="Register a user",
        operation_description="Create a user with email, optional handle, and password.",
        request_body=RegisterUserSerializer,
        responses={
            201: AuthResponseSerializer,
            400: "Validation error",
        },
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = UserService.register_with_password(
                email=serializer.validated_data["email"],
                first_name=serializer.validated_data.get("first_name", ""),
                last_name=serializer.validated_data.get("last_name", ""),
                handle=serializer.validated_data.get("handle"),
                password=serializer.validated_data["password"],
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Registration failed.",
                errors={"detail": exc.args[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            data=get_auth_response_data(user),
            message="Registration successful.",
            status=status.HTTP_201_CREATED,
        )


class SignInView(APIView):
    serializer_class = SignInSerializer

    @swagger_auto_schema(
        operation_summary="Sign in with username and password",
        operation_description=(
            "Authenticate with a password. The username field can be either "
            "the user's email address or handle."
        ),
        request_body=SignInSerializer,
        responses={
            200: AuthResponseSerializer,
            400: "Validation error",
        },
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = UserService.sign_in_with_password(
                username=serializer.validated_data["username"],
                password=serializer.validated_data["password"],
                request=request,
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Sign in failed.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            data=get_auth_response_data(user),
            message="Sign in successful.",
        )


class GoogleSignInView(APIView):
    serializer_class = GoogleAuthSerializer

    @swagger_auto_schema(
        operation_summary="Sign in with Google",
        operation_description=(
            "Exchange a Google OAuth authorization code for user info, "
            "create the user if needed, and return JWT tokens."
        ),
        request_body=GoogleAuthSerializer,
        responses={
            200: AuthResponseSerializer,
            400: "Invalid Google auth request",
            500: "Unexpected authentication error",
        },
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:

            google_helper = GoogleAuthService(
                redirect_uri=serializer.validated_data["redirect_uri"]
            )

            user_info = google_helper.verify_and_get_user_info(
                serializer.validated_data["auth_code"]
            )
            email = user_info["email"]
            first_name = user_info["first_name"]
            last_name = user_info["last_name"]

            user, _created = UserService.get_or_create_social_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
            )

            return CustomSuccessResponse(
                data=get_auth_response_data(user),
                message="Google sign in successful.",
            )

        except ValueError as e:
            return CustomErrorResponse(
                message="Google sign in failed.",
                errors={"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # Catch any other unexpected errors
            print(f"Authentication error: {e}")  # Log the full exception for debugging
            return CustomErrorResponse(
                message="An unexpected error occurred during authentication.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class OnboardingView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OnboardingSerializer

    @swagger_auto_schema(
        operation_summary="Complete onboarding",
        operation_description=(
            "Save the user's role on the user record and the remaining onboarding "
            "fields on the user's default brand."
        ),
        request_body=OnboardingSerializer,
        responses={
            200: OnboardingResponseSerializer,
            400: "Validation error",
            401: "Authentication credentials were not provided or are invalid.",
        },
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, brand = OnboardingService.complete_onboarding(
            user=request.user,
            role=serializer.validated_data["role"],
            industry=serializer.validated_data["industry"],
            posting_frequency=serializer.validated_data["posting_frequency"],
            primary_platform=serializer.validated_data["primary_platform"],
            team_size=serializer.validated_data["team_size"],
        )

        return CustomSuccessResponse(
            data=get_onboarding_response_data(user, brand),
            message="Onboarding completed successfully.",
        )


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get current user",
        operation_description="Return the authenticated user's profile data.",
        responses={
            200: UserResponseSerializer,
            401: "Authentication credentials were not provided or are invalid.",
        },
    )
    def get(self, request):
        user = _prefetch_user_for_serialization(request.user)
        return CustomSuccessResponse(
            data=UserSerializer(user).data,
            message="User data retrieved successfully.",
        )

    @swagger_auto_schema(
        operation_summary="Update current user",
        operation_description=(
            "Update editable profile fields for the authenticated user."
        ),
        request_body=UserUpdateSerializer,
        responses={
            200: UserResponseSerializer,
            400: "Validation error",
            401: "Authentication credentials were not provided or are invalid.",
        },
    )
    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        user = _prefetch_user_for_serialization(request.user)
        return CustomSuccessResponse(
            data=UserSerializer(user).data,
            message="User data updated successfully.",
        )


class PasswordResetViewSet(viewsets.ViewSet):
    """ViewSet for the password reset flow with OTP verification.

    Provides three actions:
    - `request_otp`: Send a 6-digit OTP to the user's email
    - `verify_otp`: Verify the OTP and get a reset token
    - `reset`: Reset the password using the reset token
    """

    @swagger_auto_schema(
        operation_summary="Request password reset OTP",
        operation_description=(
            "Send a 6-digit OTP to the user's email to initiate password reset. "
            "Always returns 200 for security (does not reveal if email exists). "
            "Rate-limited to 1 request per 60 seconds per email."
        ),
        request_body=RequestResetOTPSerializer,
        responses={
            200: "OTP sent successfully (or email does not exist)",
            400: "Validation error",
        },
    )
    @action(
        detail=False, methods=["post"], url_path="request-otp", url_name="request-otp"
    )
    def request_otp(self, request):
        serializer = RequestResetOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            PasswordResetService.send_reset_otp(
                email=serializer.validated_data["email"],
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to send verification code.",
                errors={"detail": exc.args[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            message=(
                "If an account with this email exists, "
                "a verification code has been sent."
            ),
        )

    @swagger_auto_schema(
        operation_summary="Verify password reset OTP",
        operation_description=(
            "Verify the 6-digit OTP sent to the user's email. "
            "On success, returns a short-lived reset token that must be used "
            "within 5 minutes to reset the password. "
            "Max 5 incorrect attempts before the OTP is invalidated."
        ),
        request_body=VerifyResetOTPSerializer,
        responses={
            200: VerifyOTPResponseSerializer,
            400: "Invalid or expired OTP",
        },
    )
    @action(
        detail=False, methods=["post"], url_path="verify-otp", url_name="verify-otp"
    )
    def verify_otp(self, request):
        serializer = VerifyResetOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reset_token = PasswordResetService.verify_reset_otp(
                email=serializer.validated_data["email"],
                otp=serializer.validated_data["otp"],
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Verification failed.",
                errors={"detail": exc.args[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            data={"reset_token": reset_token},
            message="Verification successful. You can now reset your password.",
        )

    @swagger_auto_schema(
        operation_summary="Reset password",
        operation_description=(
            "Reset the user's password using the reset token obtained "
            "from OTP verification. The new password must meet Django's "
            "password validation requirements."
        ),
        request_body=ResetPasswordSerializer,
        responses={
            200: "Password reset successful",
            400: "Invalid token or password validation error",
        },
    )
    @action(detail=False, methods=["post"], url_path="reset", url_name="reset")
    def reset(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            PasswordResetService.reset_password(
                reset_token=serializer.validated_data["reset_token"],
                new_password=serializer.validated_data["new_password"],
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Password reset failed.",
                errors={"detail": exc.args[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            message="Password reset successful. You can now sign in with your new password.",
        )
