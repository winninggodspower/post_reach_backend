from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from users.services import OnboardingService
from utils.responses import CustomErrorResponse, CustomSuccessResponse
from users.views.utils import get_onboarding_response_data, _prefetch_user_for_serialization

from users.serializers import (
    OnboardingResponseSerializer,
    OnboardingSerializer,
    UserResponseSerializer,
    UserSerializer,
    UserUpdateSerializer,
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
