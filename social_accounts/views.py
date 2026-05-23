from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema

from social_accounts.services.social_account_connection_service import SocialAccountConnectionService
from social_accounts.serializers import FacebookAuthCodeSerializer, GoogleAuthCodeSerializer, InstagramAuthCodeSerializer
from social_ploadify_backend.responses import CustomErrorResponse, CustomSuccessResponse
from social_accounts.serializers import LinkedinAuthCodeSerializer

# Create your views here.

# --- Youtube Auth View ---
class YoutubeAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GoogleAuthCodeSerializer

    @swagger_auto_schema(request_body=serializer_class)
    def post(self, request, *args, **kwargs):
        # vaidate data
        serializer = GoogleAuthCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # --- Brand ownership verification ---
        brand = serializer.validated_data["brand"]
        if brand.user != request.user:
            return CustomErrorResponse(
                {
                    "message": "You do not have permission to access this brand.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            SocialAccountConnectionService.connect_youtube(
                user=request.user,
                brand=brand,
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
                "message": "YouTube account successfully connected",
                "account_type": "youtube",
                "is_connected": True,
            },
            status=status.HTTP_200_OK,
        )


# --- Facebook Auth View ---
class FacebookAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FacebookAuthCodeSerializer

    @swagger_auto_schema(request_body=serializer_class)
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # --- Brand ownership verification ---
        brand = serializer.validated_data["brand"]
        if brand.user != request.user:
            return CustomErrorResponse(
                {
                    "message": "You do not have permission to access this brand.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            SocialAccountConnectionService.connect_facebook(
                user=request.user,
                brand=brand,
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
                "account_type": "facebook",
                "is_connected": True,
            }
        )

class InstagramAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramAuthCodeSerializer

    @swagger_auto_schema(request_body=serializer_class)
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # --- Brand ownership verification ---
        brand = serializer.validated_data["brand"]
        if brand.user != request.user:
            return CustomErrorResponse(
                {
                    "message": "You do not have permission to access this brand.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            SocialAccountConnectionService.connect_instagram(
                user=request.user,
                brand=brand,
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
                "account_type": "instagram",
                "is_connected": True,
            }
        )

class TiktokAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramAuthCodeSerializer

    def post(self, request):
        # Deserialize the incoming data
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extract the authorization code
        code = serializer.validated_data["code"]
        try:
            SocialAccountConnectionService.connect_tiktok(
                user=request.user,
                brand=serializer.validated_data["brand"],
                code=code,
            )
        except ValueError as e:
            return CustomSuccessResponse({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return CustomSuccessResponse({
            "message": "TikTok account successfully connected",
            "account_type": "tiktok",
            "is_connected": True,
        }, status=status.HTTP_200_OK)

class LinkedinAuthConnectView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LinkedinAuthCodeSerializer

    @swagger_auto_schema(request_body=serializer_class)
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # --- Brand ownership verification ---
        brand = serializer.validated_data["brand"]
        if brand.user != request.user:
            return CustomErrorResponse(
                {"message": "You do not have permission to access this brand."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            SocialAccountConnectionService.connect_linkedin(
                user=request.user,
                brand=brand,
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
                "account_type": "linkedin",
                "is_connected": True,
            },
            status=status.HTTP_200_OK,
        )
