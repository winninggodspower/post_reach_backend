from drf_yasg.utils import swagger_auto_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status

from integrations.services.google_auth_service import GoogleAuthService
from users.services import OnboardingService, UserService
from utils.responses import CustomErrorResponse, CustomSuccessResponse
from .serializers import (
    AuthResponseSerializer,
    BrandSerializer,
    GoogleAuthSerializer,
    OnboardingResponseSerializer,
    OnboardingSerializer,
    RegisterUserSerializer,
    SignInSerializer,
    UserResponseSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

# Create your views here.
def get_auth_response_data(user):
    return {
        'user': UserSerializer(user).data,
        'tokens': UserService.get_auth_tokens(user),
    }


def get_onboarding_response_data(user, brand):
    return {
        "user": UserSerializer(user).data,
        "brand": BrandSerializer(brand).data,
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
                email=serializer.validated_data['email'],
                first_name=serializer.validated_data.get('first_name', ''),
                last_name=serializer.validated_data.get('last_name', ''),
                handle=serializer.validated_data.get('handle'),
                password=serializer.validated_data['password'],
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Registration failed.",
                errors={'detail': exc.args[0]},
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
                username=serializer.validated_data['username'],
                password=serializer.validated_data['password'],
                request=request,
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Sign in failed.",
                errors={'detail': str(exc)},
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
                redirect_uri=serializer.validated_data['redirect_uri']
            )

            user_info = google_helper.verify_and_get_user_info(
                serializer.validated_data['auth_code']
            )
            email = user_info['email']
            first_name = user_info['first_name']
            last_name = user_info['last_name']

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
                errors={'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # Catch any other unexpected errors
            print(f"Authentication error: {e}")  # Log the full exception for debugging
            return CustomErrorResponse(
                message='An unexpected error occurred during authentication.',
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
        return CustomSuccessResponse(
            data=UserSerializer(request.user).data,
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

        return CustomSuccessResponse(
            data=UserSerializer(request.user).data,
            message="User data updated successfully.",
        )
