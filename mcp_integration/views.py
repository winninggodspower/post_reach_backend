from drf_yasg.utils import swagger_auto_schema
from mcp_server.views import MCPServerStreamableHttpView
from oauth2_provider.contrib.rest_framework import (
    OAuth2ProtectedResourceAuthentication,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from mcp_integration.serializers import OAuthConnectionSerializer
from mcp_integration.services import OAuthConnectionService
from utils.responses import CustomErrorResponse, CustomSuccessResponse


class PostGleeMCPView(MCPServerStreamableHttpView):
    """
    Protected MCP Streamable HTTP endpoint.
    Authenticates requests via OAuth 2.1 Bearer tokens and advertises
    `/.well-known/oauth-protected-resource` in `WWW-Authenticate` on 401.
    """

    authentication_classes = [OAuth2ProtectedResourceAuthentication]
    permission_classes = [IsAuthenticated]


class OAuthConnectionListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List connected OAuth / MCP applications",
        operation_description=(
            "Returns all AI / MCP applications that currently hold active OAuth "
            "tokens on behalf of the authenticated user."
        ),
        responses={200: OAuthConnectionSerializer(many=True)},
    )
    def get(self, request):
        connections = OAuthConnectionService.list_connections(request.user)
        serializer = OAuthConnectionSerializer(connections, many=True)
        return CustomSuccessResponse(
            data=serializer.data,
            message="Connected applications retrieved successfully.",
        )


class OAuthConnectionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Revoke a connected OAuth / MCP application",
        operation_description=(
            "Revokes all active access and refresh tokens granted by the authenticated "
            "user to the specified OAuth client_id."
        ),
        responses={
            200: "Connection revoked successfully",
            404: "Connected application not found",
        },
    )
    def delete(self, request, client_id: str):
        try:
            OAuthConnectionService.revoke_connection(request.user, client_id)
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc),
                errors={"detail": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        return CustomSuccessResponse(
            message="Application access revoked successfully.",
        )

