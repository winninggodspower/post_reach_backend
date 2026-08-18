from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView

from integrations.services.google_auth_service import GoogleAuthService
from users.serializers import (
    AuthResponseSerializer,
    GoogleAuthSerializer,
    RegisterUserSerializer,
    RequestResetOTPSerializer,
    ResetPasswordSerializer,
    SignInSerializer,
    VerifyOTPResponseSerializer,
    VerifyResetOTPSerializer,
)
from users.services import PasswordResetService, UserService
from users.views.utils import get_auth_response_data
from utils.responses import CustomErrorResponse, CustomSuccessResponse


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
            print(f"Authentication error: {e}")
            return CustomErrorResponse(
                message="An unexpected error occurred during authentication.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PasswordResetViewSet(viewsets.ViewSet):
    @swagger_auto_schema(
        operation_summary="Request password reset OTP",
        operation_description=(
            "Send a 6-digit OTP to the user's email to initiate password reset. "
            "Always returns 200 for security."
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
        operation_description=("Verify the 6-digit OTP sent to the user's email."),
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
        operation_description=("Reset the user's password using the reset token."),
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
