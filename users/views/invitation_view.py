from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from users.serializers import (
    AuthResponseSerializer,
    BrandInvitationSerializer,
    BrandMemberSerializer,
    InvitationDetailsSerializer,
    RegisterInvitationSerializer,
    SendInvitationSerializer,
    UpdateMemberRoleSerializer,
)
from users.services.invitation_service import BrandInvitationService
from users.views.utils import get_auth_response_data
from utils.responses import CustomErrorResponse, CustomSuccessResponse

User = get_user_model()


class BrandInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List brand invitations",
        operation_description="Get invitations for a brand. Excludes revoked and accepted invitations by default. Filter by passing ?status=<pending|expired|revoked|accepted|all>.",
        manual_parameters=[
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by invitation status (pending, expired, revoked, accepted, all).",
                type=openapi.TYPE_STRING,
                required=False,
            )
        ],
        responses={
            200: BrandInvitationSerializer(many=True),
            400: "Permission denied or brand not found",
            401: "Unauthorized",
        },
    )
    def get(self, request, brand_id):
        try:
            status_param = request.query_params.get("status")
            invitations = BrandInvitationService.list_brand_invitations(
                user=request.user, brand_id=brand_id, status=status_param
            )
            return CustomSuccessResponse(
                data=BrandInvitationSerializer(invitations, many=True).data,
                message="Brand invitations retrieved successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc),
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @swagger_auto_schema(
        operation_summary="Send brand invitation",
        operation_description="Invite a collaborator by email to join the brand with a specific role.",
        request_body=SendInvitationSerializer,
        responses={
            201: BrandInvitationSerializer,
            400: "Validation or permission error",
            401: "Unauthorized",
        },
    )
    def post(self, request, brand_id):
        serializer = SendInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation = BrandInvitationService.send_invitation(
                inviter=request.user,
                brand_id=brand_id,
                email=serializer.validated_data["email"],
                role=serializer.validated_data.get("role"),
            )
            return CustomSuccessResponse(
                data=BrandInvitationSerializer(invitation).data,
                message="Invitation sent successfully.",
                status=status.HTTP_201_CREATED,
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to send invitation.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RevokeInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Revoke brand invitation",
        operation_description="Revoke an existing pending invitation.",
        responses={
            200: "Invitation revoked successfully",
            400: "Invalid invitation or permission denied",
            401: "Unauthorized",
        },
    )
    def delete(self, request, brand_id, invitation_id):
        try:
            BrandInvitationService.revoke_invitation(
                user=request.user, brand_id=brand_id, invitation_id=invitation_id
            )
            return CustomSuccessResponse(
                message="Invitation revoked successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to revoke invitation.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResendInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Resend brand invitation",
        operation_description="Regenerate token, reset expiration to 7 days, and resend invitation email.",
        responses={
            200: BrandInvitationSerializer,
            400: "Invalid invitation or permission denied",
            401: "Unauthorized",
        },
    )
    def post(self, request, brand_id, invitation_id):
        try:
            invitation = BrandInvitationService.resend_invitation(
                user=request.user, brand_id=brand_id, invitation_id=invitation_id
            )
            return CustomSuccessResponse(
                data=BrandInvitationSerializer(invitation).data,
                message="Invitation resent successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to resend invitation.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class BrandMemberListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List brand members",
        operation_description="Get all members and collaborators of a brand.",
        responses={
            200: BrandMemberSerializer(many=True),
            400: "Permission denied or brand not found",
            401: "Unauthorized",
        },
    )
    def get(self, request, brand_id):
        try:
            members = BrandInvitationService.list_brand_members(
                user=request.user, brand_id=brand_id
            )
            return CustomSuccessResponse(
                data=BrandMemberSerializer(members, many=True).data,
                message="Brand members retrieved successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message=str(exc),
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class BrandMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Update brand member role",
        operation_description="Change a collaborator's role within the brand.",
        request_body=UpdateMemberRoleSerializer,
        responses={
            200: BrandMemberSerializer,
            400: "Validation or permission error",
            401: "Unauthorized",
        },
    )
    def patch(self, request, brand_id, member_id):
        serializer = UpdateMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            member = BrandInvitationService.update_member_role(
                user=request.user,
                brand_id=brand_id,
                member_id=member_id,
                new_role=serializer.validated_data["role"],
            )
            return CustomSuccessResponse(
                data=BrandMemberSerializer(member).data,
                message="Member role updated successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to update member role.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @swagger_auto_schema(
        operation_summary="Remove brand member",
        operation_description="Remove a collaborator from the brand or leave the brand.",
        responses={
            200: "Member removed successfully",
            400: "Permission denied or member not found",
            401: "Unauthorized",
        },
    )
    def delete(self, request, brand_id, member_id):
        try:
            BrandInvitationService.remove_member(
                user=request.user, brand_id=brand_id, member_id=member_id
            )
            return CustomSuccessResponse(
                message="Member removed successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to remove member.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class InvitationDetailsView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Get invitation details",
        operation_description="Public endpoint to fetch metadata about an invitation token for the accept landing page.",
        responses={
            200: InvitationDetailsSerializer,
            400: "Invalid or expired invitation token",
        },
    )
    def get(self, request, token):
        try:
            invitation = BrandInvitationService.get_invitation_by_token(token)
            user_exists = User.objects.filter(email__iexact=invitation.email).exists()
            payload = {
                "id": invitation.id,
                "brand_id": invitation.brand_id,
                "brand_name": invitation.brand.name,
                "brand_logo_url": invitation.brand.logo_url,
                "email": invitation.email,
                "role": invitation.role,
                "inviter_name": (
                    invitation.invited_by.get_full_name()
                    or invitation.invited_by.handle
                    or invitation.invited_by.email
                ),
                "inviter_email": invitation.invited_by.email,
                "expires_at": invitation.expires_at,
                "is_expired": invitation.expires_at <= timezone.now(),
                "user_exists": user_exists,
            }
            serializer = InvitationDetailsSerializer(payload)
            return CustomSuccessResponse(
                data=serializer.data,
                message="Invitation details retrieved successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Invalid invitation link.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class AcceptInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Accept brand invitation",
        operation_description="Accept an invitation as an authenticated user.",
        responses={
            200: BrandMemberSerializer,
            400: "Invalid token, expired, or email mismatch",
            401: "Authentication required",
        },
    )
    def post(self, request, token):
        try:
            member, brand = BrandInvitationService.accept_invitation(
                token=token, user=request.user
            )
            return CustomSuccessResponse(
                data=BrandMemberSerializer(member).data,
                message=f"You have joined {brand.name} successfully.",
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Failed to accept invitation.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RegisterAndAcceptInvitationView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Register and accept brand invitation",
        operation_description="Create a new user account using invitation details and join the brand in a single step.",
        request_body=RegisterInvitationSerializer,
        responses={
            201: AuthResponseSerializer,
            400: "Validation error or invalid token",
        },
    )
    def post(self, request, token):
        serializer = RegisterInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user, _ = BrandInvitationService.register_and_accept_invitation(
                token=token,
                password=serializer.validated_data["password"],
                first_name=serializer.validated_data.get("first_name", ""),
                last_name=serializer.validated_data.get("last_name", ""),
                handle=serializer.validated_data.get("handle"),
            )
            return CustomSuccessResponse(
                data=get_auth_response_data(user),
                message="Account registered and invitation accepted successfully.",
                status=status.HTTP_201_CREATED,
            )
        except ValueError as exc:
            return CustomErrorResponse(
                message="Registration failed.",
                errors={"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
