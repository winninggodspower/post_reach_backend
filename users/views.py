from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from integrations.services.google_auth_service import GoogleAuthService
from users.services import UserService
from .serializers import (
    AuthTokenSerializer,
    GoogleAuthSerializer,
    RegisterUserSerializer,
    SignInSerializer,
)

# Create your views here.
class RegisterUserView(APIView):
    serializer_class = RegisterUserSerializer

    @swagger_auto_schema(
        operation_summary="Register a user",
        operation_description="Create a user with email, optional handle, and password.",
        request_body=RegisterUserSerializer,
        responses={
            201: AuthTokenSerializer,
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
            return Response({'detail': exc.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            UserService.get_auth_tokens(user),
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
            200: AuthTokenSerializer,
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
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        tokens = UserService.get_auth_tokens(user)
        return Response(tokens)


class GoogleLoginView(APIView):
    serializer_class = GoogleAuthSerializer

    @swagger_auto_schema(
        operation_summary="Sign in with Google",
        operation_description=(
            "Exchange a Google OAuth authorization code for user info, "
            "create the user if needed, and return JWT tokens."
        ),
        request_body=GoogleAuthSerializer,
        responses={
            200: AuthTokenSerializer,
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

            user, created = UserService.get_or_create_social_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
            )

            # Return JWT token
            return Response(UserService.get_auth_tokens(user))

        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Catch any other unexpected errors
            print(f"Authentication error: {e}")  # Log the full exception for debugging
            return Response(
                {'detail': 'An unexpected error occurred during authentication.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
