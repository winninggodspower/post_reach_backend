from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from integrations.providers.youtube_service import YoutubeService
from social_accounts.manual_parameters import redirect_uri_param
from social_accounts.services.social_account_connection_service import SocialAccountConnectionService
from social_accounts.serializers import (
    ConnectAccountResponseSerializer,
    FacebookAuthCodeSerializer,
    GoogleAuthCodeSerializer,
    InstagramAuthCodeSerializer,
    LinkedinAuthCodeSerializer,
    YoutubeAuthUrlResponseSerializer,
)


from utils.responses import CustomErrorResponse, CustomSuccessResponse

# Create your views here.


# --- Youtube Auth ViewSet ---
class YoutubeAuthViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="auth-url")
    @swagger_auto_schema(
        operation_summary="Get YouTube OAuth URL",
        operation_description="Generates a Google OAuth authorization URL for connecting a YouTube account.",
        manual_parameters=[redirect_uri_param],
        responses={
            200: YoutubeAuthUrlResponseSerializer,
            400: "Missing redirect_uri parameter",
        },
    )
    def auth_url(self, request):
        """
        GET /social/youtube/auth-url/?redirect_uri=...
        Returns the Google OAuth URL for the user to authorize the app.
        """
        redirect_uri = request.query_params.get("redirect_uri")
        if not redirect_uri:
            return CustomErrorResponse(
                {"message": "redirect_uri query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            auth_url = YoutubeService.generate_auth_url(
                user_id=request.user.id,
                redirect_uri=redirect_uri,
            )
        except Exception as e:
            return CustomErrorResponse(
                {"message": f"Failed to generate auth URL: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return CustomSuccessResponse(
            {"auth_url": auth_url},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="connect")
    @swagger_auto_schema(
        request_body=GoogleAuthCodeSerializer,
        responses={200: ConnectAccountResponseSerializer},
    )
    def connect(self, request):
        """
        POST /social/youtube/connect/
        Exchanges the authorization code for tokens and saves the social account.
        """
        serializer = GoogleAuthCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            YoutubeService.connect_account(
                user=request.user,
                auth_code=serializer.validated_data["code"],
                redirect_uri=serializer.validated_data["redirect_uri"],
                state=serializer.validated_data.get("state"),
                brand=serializer.validated_data.get("brand"),
            )
        except (PermissionError, ValueError) as e:
            status_code = status.HTTP_403_FORBIDDEN if isinstance(e, PermissionError) else status.HTTP_400_BAD_REQUEST
            return CustomErrorResponse(
                {"message": str(e)},
                status=status_code,
            )

        return CustomSuccessResponse(
            {
                "message": "YouTube account successfully connected",
                "platform": "youtube",
                "is_connected": True,
            },
            status=status.HTTP_200_OK,
        )


# --- Facebook Auth View ---
class FacebookAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FacebookAuthCodeSerializer

    @swagger_auto_schema(
        request_body=serializer_class,
        responses={200: ConnectAccountResponseSerializer},

    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            SocialAccountConnectionService.connect_facebook(
                user=request.user,
                brand=serializer.validated_data.get("brand"),
                short_lived_access_token=serializer.validated_data["short_lived_access_token"],
            )
        except ValueError as e:
            return CustomErrorResponse(
                {
                    "message": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return CustomSuccessResponse(
            {
                "message": "Facebook account successfully connected",
                "platform": "facebook",
                "is_connected": True,
            }
        )


class InstagramAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramAuthCodeSerializer

    @swagger_auto_schema(
        request_body=serializer_class,
        responses={200: ConnectAccountResponseSerializer},

    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            SocialAccountConnectionService.connect_instagram(
                user=request.user,
                brand=serializer.validated_data.get("brand"),
                auth_code=serializer.validated_data["code"],
                redirect_uri=serializer.validated_data["redirect_uri"],
            )
        except ValueError as e:
            return CustomErrorResponse(
                {
                    "message": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            {
                "message": "Instagram account successfully connected",
                "platform": "instagram",
                "is_connected": True,
            }
        )


class TiktokAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramAuthCodeSerializer

    @swagger_auto_schema(
        request_body=serializer_class,
        responses={200: ConnectAccountResponseSerializer},

    )
    def post(self, request):

        # Deserialize the incoming data
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"]
        try:
            SocialAccountConnectionService.connect_tiktok(
                user=request.user,
                brand=serializer.validated_data.get("brand"),
                code=code,
            )
        except ValueError as e:
            return CustomSuccessResponse({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return CustomSuccessResponse({
            "message": "TikTok account successfully connected",
            "platform": "tiktok",
            "is_connected": True,
        }, status=status.HTTP_200_OK)

class LinkedinAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LinkedinAuthCodeSerializer

    @swagger_auto_schema(
        request_body=serializer_class,
        responses={200: ConnectAccountResponseSerializer},

    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            SocialAccountConnectionService.connect_linkedin(
                user=request.user,
                brand=serializer.validated_data.get("brand"),
                code=serializer.validated_data["code"],
                redirect_uri=serializer.validated_data["redirect_uri"],
            )
        except ValueError as e:
            return CustomErrorResponse(
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            {
                "message": "LinkedIn account successfully connected",
                "platform": "linkedin",
                "is_connected": True,
            },
            status=status.HTTP_200_OK,
        )


