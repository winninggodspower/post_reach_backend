from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from developers.serializers import (
    ApplicationCreateSerializer,
    ApplicationSerializer,
    ApplicationUpdateSerializer,
    RegenerateSecretResponseSerializer,
)
from developers.services import DeveloperApplicationService
from utils.responses import CustomErrorResponse, CustomSuccessResponse


class DeveloperApplicationListCreateView(APIView):
    """List or create OAuth applications for the authenticated developer."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List developer OAuth applications",
        operation_description="Returns all OAuth applications registered by the authenticated developer.",
        responses={200: ApplicationSerializer(many=True)},
    )
    def get(self, request):
        apps = DeveloperApplicationService.list_applications(request.user)
        serializer = ApplicationSerializer(apps, many=True)
        return CustomSuccessResponse(
            data=serializer.data,
            message="Developer applications retrieved successfully.",
        )

    @swagger_auto_schema(
        operation_summary="Create developer OAuth application",
        operation_description=(
            "Creates a new OAuth application for the developer. If client_type is 'confidential', "
            "a client_secret is generated and returned once in the response. Store it securely."
        ),
        request_body=ApplicationCreateSerializer,
        responses={201: ApplicationSerializer, 400: "Validation error"},
    )
    def post(self, request):
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            app = DeveloperApplicationService.create_application(
                user=request.user,
                data=serializer.validated_data,
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to create application.",
                errors=(
                    exc.args[0]
                    if isinstance(exc.args[0], dict)
                    else {"detail": str(exc)}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = ApplicationSerializer(app)
        return CustomSuccessResponse(
            data=response_serializer.data,
            message="Application created successfully. Copy your client secret now if your application is confidential.",
            status=status.HTTP_201_CREATED,
        )


class DeveloperApplicationDetailView(APIView):
    """Retrieve, update, or delete a developer OAuth application."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get application details",
        operation_description="Returns details for the specified OAuth application owned by the developer.",
        responses={200: ApplicationSerializer, 404: "Application not found"},
    )
    def get(self, request, client_id: str):
        try:
            app = DeveloperApplicationService.get_application(request.user, client_id)
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_404_NOT_FOUND
            )

        serializer = ApplicationSerializer(app)
        return CustomSuccessResponse(
            data=serializer.data, message="Application details retrieved successfully."
        )

    @swagger_auto_schema(
        operation_summary="Update developer OAuth application",
        operation_description="Updates the application name, redirect URIs, or allowed origins.",
        request_body=ApplicationUpdateSerializer,
        responses={
            200: ApplicationSerializer,
            400: "Validation error",
            404: "Application not found",
        },
    )
    def patch(self, request, client_id: str):
        serializer = ApplicationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            app = DeveloperApplicationService.update_application(
                user=request.user,
                client_id=client_id,
                data=serializer.validated_data,
            )
        except ValueError as exc:
            if "not found" in str(exc).lower():
                return CustomErrorResponse(
                    message=str(exc), status=status.HTTP_404_NOT_FOUND
                )
            return CustomErrorResponse(
                message="Failed to update application.",
                errors=(
                    exc.args[0]
                    if isinstance(exc.args[0], dict)
                    else {"detail": str(exc)}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = ApplicationSerializer(app)
        return CustomSuccessResponse(
            data=response_serializer.data, message="Application updated successfully."
        )

    @swagger_auto_schema(
        operation_summary="Delete developer OAuth application",
        operation_description="Deletes the application and immediately revokes all active tokens issued to it.",
        responses={
            200: "Application deleted successfully",
            404: "Application not found",
        },
    )
    def delete(self, request, client_id: str):
        try:
            DeveloperApplicationService.delete_application(request.user, client_id)
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc), status=status.HTTP_404_NOT_FOUND
            )

        return CustomSuccessResponse(
            message="Application deleted successfully and all active tokens were revoked."
        )


class DeveloperApplicationSecretRegenerateView(APIView):
    """Regenerates the client secret for a confidential application."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Regenerate client secret",
        operation_description="Generates a new client secret for a confidential application, invalidating the old one.",
        responses={
            200: RegenerateSecretResponseSerializer,
            400: "Public clients cannot have secrets",
            404: "Not found",
        },
    )
    def post(self, request, client_id: str):
        try:
            new_secret = DeveloperApplicationService.regenerate_client_secret(
                request.user, client_id
            )
        except ValueError as exc:
            err_msg = str(exc)
            status_code = (
                status.HTTP_404_NOT_FOUND
                if "not found" in err_msg.lower()
                else status.HTTP_400_BAD_REQUEST
            )
            return CustomErrorResponse(message=err_msg, status=status_code)

        data = {
            "client_id": client_id,
            "client_secret": new_secret,
            "message": "Client secret regenerated successfully. Make sure to save it now.",
        }
        return CustomSuccessResponse(
            data=data, message="Client secret regenerated successfully."
        )


class DeveloperScopesView(APIView):
    """Discovery endpoint listing all available OAuth scopes supported by PostGlee."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List available OAuth scopes",
        operation_description="Returns the platform's supported OAuth scopes, names, and descriptions for developer apps.",
    )
    def get(self, request):
        raw_scopes = settings.OAUTH2_PROVIDER.get("SCOPES", {})
        friendly_names = {
            "accounts:read": "Read Brands & Accounts",
            "posts:read": "Read Posts & Calendar",
            "posts:write": "Publish & Edit Posts",
        }
        scopes_list = [
            {
                "scope": scope_key,
                "name": friendly_names.get(
                    scope_key, scope_key.replace(":", " ").title()
                ),
                "description": desc,
            }
            for scope_key, desc in raw_scopes.items()
        ]
        return CustomSuccessResponse(
            data=scopes_list, message="Supported scopes retrieved successfully."
        )
