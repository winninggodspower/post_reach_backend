from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from integrations.providers.facebook_service import FacebookService
from integrations.providers.instagram_service import InstagramService
from integrations.providers.youtube_service import YoutubeService
from social_accounts.services.social_account_connection_service import SocialAccountConnectionService
from social_accounts.serializers import (
    ConnectAccountResponseSerializer,
    FacebookAuthCodeSerializer,
    FacebookAuthUrlResponseSerializer,
    FacebookPagesListResponseSerializer,
    FacebookPagesRequestSerializer,
    GoogleAuthCodeSerializer,
    InstagramAuthCodeSerializer,
    InstagramAuthUrlResponseSerializer,
    LinkedinAuthCodeSerializer,
    LinkedinAuthUrlResponseSerializer,
    TiktokAuthCodeSerializer,
    TiktokAuthUrlResponseSerializer,
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
        operation_description="Generates a Google OAuth authorization URL for connecting a YouTube account. The redirect URI is automatically resolved from the backend settings.",
        responses={
            200: YoutubeAuthUrlResponseSerializer,
        },
    )
    def auth_url(self, request):
        """
        GET /social-accounts/youtube/auth-url/
        Returns the Google OAuth URL for the user to authorize the app.
        The redirect URI is resolved from backend settings automatically.
        """
        try:
            auth_url = YoutubeService.generate_auth_url(
                user_id=request.user.id,
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
        POST /social-accounts/youtube/connect/
        Exchanges the authorization code for tokens and saves the social account.
        """
        serializer = GoogleAuthCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            YoutubeService.connect_account(
                user=request.user,
                auth_code=serializer.validated_data["code"],
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


# --- Facebook Auth ViewSet ---
class FacebookAuthViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="auth-url")
    @swagger_auto_schema(
        operation_summary="Get Facebook OAuth URL",
        operation_description="Generates a Facebook OAuth authorization URL for connecting a Facebook account.",
        responses={
            200: FacebookAuthUrlResponseSerializer,
        },
    )
    def auth_url(self, request):
        """
        GET /social-accounts/facebook/auth-url/
        Returns the Facebook OAuth URL for the user to authorize the app.
        The redirect URI is resolved from backend settings automatically.
        """
        try:
            auth_url = FacebookService.generate_auth_url(
                user_id=request.user.id,
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
        request_body=FacebookAuthCodeSerializer,
        responses={200: ConnectAccountResponseSerializer},
    )
    def connect(self, request):
        """
        POST /social-accounts/facebook/connect/
        Exchanges the authorization code for a long-lived token and saves the social account.
        """
        serializer = FacebookAuthCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            SocialAccountConnectionService.connect_facebook(
                user=request.user,
                brand=serializer.validated_data.get("brand"),
                code=serializer.validated_data["code"],
                redirect_uri=serializer.validated_data["redirect_uri"],
                page_id=serializer.validated_data.get("page_id", ""),
            )
        except ValueError as e:
            return CustomErrorResponse(
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            {
                "message": "Facebook account successfully connected",
                "platform": "facebook",
                "is_connected": True,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="pages")
    @swagger_auto_schema(
        request_body=FacebookPagesRequestSerializer,
        responses={200: FacebookPagesListResponseSerializer},
    )
    def pages(self, request):
        """
        POST /social-accounts/facebook/pages/
        Exchanges the authorization code for a long-lived token and returns
        the list of Facebook Pages the user manages, including their IDs and names.
        The user can then select a page and pass its ID to the connect endpoint.
        """
        serializer = FacebookPagesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            long_lived_token, _ = FacebookService.exchange_code_for_token(
                serializer.validated_data["code"],
                serializer.validated_data["redirect_uri"],
            )
            pages = FacebookService.get_facebook_pages(long_lived_token)
        except ValueError as e:
            return CustomErrorResponse(
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Strip access_tokens from response — not needed by the frontend at this stage
        safe_pages = [
            {"id": p["id"], "name": p["name"], "picture_url": p["picture_url"]}
            for p in pages
        ]

        return CustomSuccessResponse(
            {"pages": safe_pages},
            status=status.HTTP_200_OK,
        )


# --- Instagram Auth ViewSet ---
class InstagramAuthViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="auth-url")
    @swagger_auto_schema(
        operation_summary="Get Instagram OAuth URL",
        operation_description="Generates an Instagram OAuth authorization URL for connecting an Instagram account. The redirect URI is automatically resolved from the backend settings.",
        responses={
            200: InstagramAuthUrlResponseSerializer,
        },
    )
    def auth_url(self, request):
        """
        GET /social-accounts/instagram/auth-url/
        Returns the Instagram OAuth URL for the user to authorize the app.
        The redirect URI is resolved from backend settings automatically.
        """
        try:
            auth_url = InstagramService.generate_auth_url(
                user_id=request.user.id,
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
        request_body=InstagramAuthCodeSerializer,
        responses={200: ConnectAccountResponseSerializer},
    )
    def connect(self, request):
        """
        POST /social-accounts/instagram/connect/
        Exchanges the authorization code for tokens and saves the social account.
        """
        serializer = InstagramAuthCodeSerializer(data=request.data)
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
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return CustomSuccessResponse(
            {
                "message": "Instagram account successfully connected",
                "platform": "instagram",
                "is_connected": True,
            },
            status=status.HTTP_200_OK,
        )


# --- TikTok Auth ViewSet ---
class TiktokAuthViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="auth-url")
    @swagger_auto_schema(
        operation_summary="Get TikTok OAuth URL",
        operation_description="Generates a TikTok OAuth authorization URL for connecting a TikTok account. The redirect URI is automatically resolved from the backend settings.",
        responses={
            200: TiktokAuthUrlResponseSerializer,
        },
    )
    def auth_url(self, request):
        """
        GET /social-accounts/tiktok/auth-url/
        Returns the TikTok OAuth URL for the user to authorize the app.
        The redirect URI is resolved from backend settings automatically.
        """
        from integrations.providers.tiktok_service import TiktokService

        try:
            auth_url = TiktokService.generate_auth_url(
                user_id=request.user.id,
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
        request_body=TiktokAuthCodeSerializer,
        responses={200: ConnectAccountResponseSerializer},
    )
    def connect(self, request):
        """
        POST /social-accounts/tiktok/connect/
        Exchanges the authorization code for tokens and saves the social account.
        """
        serializer = TiktokAuthCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            SocialAccountConnectionService.connect_tiktok(
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
                "message": "TikTok account successfully connected",
                "platform": "tiktok",
                "is_connected": True,
            },
            status=status.HTTP_200_OK,
        )


# --- LinkedIn Auth ViewSet ---
class LinkedinAuthViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="auth-url")
    @swagger_auto_schema(
        operation_summary="Get LinkedIn OAuth URL",
        operation_description="Generates a LinkedIn OAuth authorization URL for connecting a LinkedIn account. The redirect URI is automatically resolved from the backend settings.",
        responses={
            200: LinkedinAuthUrlResponseSerializer,
        },
    )
    def auth_url(self, request):
        """
        GET /social-accounts/linkedin/auth-url/
        Returns the LinkedIn OAuth URL for the user to authorize the app.
        The redirect URI is resolved from backend settings automatically.
        """
        from integrations.providers.linkedin_service import LinkedinService

        try:
            auth_url = LinkedinService.generate_auth_url(
                user_id=request.user.id,
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
        request_body=LinkedinAuthCodeSerializer,
        responses={200: ConnectAccountResponseSerializer},
    )
    def connect(self, request):
        """
        POST /social-accounts/linkedin/connect/
        Exchanges the authorization code for tokens and saves the social account.
        """
        serializer = LinkedinAuthCodeSerializer(data=request.data)
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


