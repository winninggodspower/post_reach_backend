from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from users.models import Brand
from users.serializers import (
    BrandSerializer,
    SetActiveBrandSerializer,
    UserResponseSerializer,
    UserSerializer,
)
from users.services import UserService
from users.services.brand_service import BrandService
from users.views.utils import _prefetch_user_for_serialization
from utils.responses import CustomErrorResponse, CustomSuccessResponse


class BrandViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BrandSerializer

    def get_queryset(self):
        return Brand.objects.filter(user=self.request.user).prefetch_related(
            "social_accounts"
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        brand = BrandService.create_brand(request.user, serializer.validated_data)
        return CustomSuccessResponse(
            data=BrandSerializer(brand).data,
            message="Brand created successfully.",
            status=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return CustomSuccessResponse(
            data=serializer.data,
            message="Brands retrieved successfully.",
        )


class SetActiveBrandView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Set active brand",
        operation_description=("Set the active brand for the current user."),
        request_body=SetActiveBrandSerializer,
        responses={
            200: UserResponseSerializer,
            400: "Validation error or Brand not found",
            401: "Authentication credentials were not provided or are invalid.",
        },
    )
    def post(self, request):
        serializer = SetActiveBrandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            UserService.set_active_brand(
                user=request.user, brand_id=serializer.validated_data["brand_id"]
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to set active brand.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = _prefetch_user_for_serialization(request.user)
        return CustomSuccessResponse(
            data=UserSerializer(user).data,
            message="Active brand updated successfully.",
        )
