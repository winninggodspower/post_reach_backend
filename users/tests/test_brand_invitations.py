from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from users.enums import BrandRoleChoices, InvitationStatusChoices
from users.models import Brand, BrandInvitation, BrandMember
from users.services.brand_service import BrandService
from users.services.invitation_service import BrandInvitationService

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def brand_owner(db):
    user = User.objects.create_user(
        email="owner@example.com",
        password="Password123!",
        first_name="Owner",
        last_name="User",
        handle="brandowner",
    )
    return user


@pytest.fixture
def brand(brand_owner):
    return BrandService.create_brand(
        user=brand_owner,
        validated_data={"name": "Acme Marketing"},
    )


@pytest.fixture
def existing_user(db):
    return User.objects.create_user(
        email="collab@example.com",
        password="Password123!",
        first_name="Collab",
        last_name="User",
        handle="collabuser",
    )


class TestBrandInvitationService:
    @patch("utils.notification_service.NotificationService.send_email")
    def test_send_invitation_success(self, mock_email, brand_owner, brand):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="newcollab@example.com",
            role=BrandRoleChoices.EDITOR,
        )

        assert invitation.email == "newcollab@example.com"
        assert invitation.role == BrandRoleChoices.EDITOR
        assert invitation.status == InvitationStatusChoices.PENDING
        assert invitation.token is not None
        assert invitation.expires_at > timezone.now() + timedelta(days=6)
        mock_email.assert_called_once()

    def test_cannot_invite_owner_or_existing_member(
        self, brand_owner, brand, existing_user
    ):
        # Cannot invite the owner
        with pytest.raises(ValueError, match="already the owner"):
            BrandInvitationService.send_invitation(
                inviter=brand_owner,
                brand_id=brand.id,
                email=brand_owner.email,
            )

        # Cannot invite existing member
        BrandMember.objects.create(
            brand=brand, user=existing_user, role=BrandRoleChoices.EDITOR
        )
        with pytest.raises(ValueError, match="already a member"):
            BrandInvitationService.send_invitation(
                inviter=brand_owner,
                brand_id=brand.id,
                email=existing_user.email,
            )

    def test_unauthorized_member_cannot_invite(self, brand_owner, brand, existing_user):
        BrandMember.objects.create(
            brand=brand, user=existing_user, role=BrandRoleChoices.VIEWER
        )
        with pytest.raises(ValueError, match="do not have permission"):
            BrandInvitationService.send_invitation(
                inviter=existing_user,
                brand_id=brand.id,
                email="another@example.com",
            )

    @patch("utils.notification_service.NotificationService.send_email")
    def test_reinviting_pending_email_updates_token(
        self, mock_email, brand_owner, brand
    ):
        invite1 = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="reinvite@example.com",
            role=BrandRoleChoices.VIEWER,
        )
        token1 = invite1.token

        invite2 = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="reinvite@example.com",
            role=BrandRoleChoices.ADMIN,
        )

        assert invite1.id == invite2.id
        assert invite2.role == BrandRoleChoices.ADMIN
        assert invite2.token != token1
        assert (
            BrandInvitation.objects.filter(
                brand=brand, email="reinvite@example.com"
            ).count()
            == 1
        )

    @patch("utils.notification_service.NotificationService.send_email")
    def test_accept_invitation_authenticated(
        self, mock_email, brand_owner, brand, existing_user
    ):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email=existing_user.email,
            role=BrandRoleChoices.EDITOR,
        )

        member, joined_brand = BrandInvitationService.accept_invitation(
            token=invitation.token,
            user=existing_user,
        )

        assert member.user == existing_user
        assert member.brand == brand
        assert member.role == BrandRoleChoices.EDITOR
        invitation.refresh_from_db()
        assert invitation.status == InvitationStatusChoices.ACCEPTED

    @patch("utils.notification_service.NotificationService.send_email")
    def test_accept_invitation_with_mismatched_email_fails(
        self, mock_email, brand_owner, brand
    ):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="intended@example.com",
            role=BrandRoleChoices.EDITOR,
        )
        other_user = User.objects.create_user(
            email="wrong@example.com",
            password="Password123!",
        )

        with pytest.raises(ValueError, match="This invitation was sent to"):
            BrandInvitationService.accept_invitation(
                token=invitation.token,
                user=other_user,
            )

    @patch("utils.notification_service.NotificationService.send_email")
    def test_expired_invitation_raises_error(
        self, mock_email, brand_owner, brand, existing_user
    ):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email=existing_user.email,
        )
        invitation.expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        with pytest.raises(ValueError, match="expired"):
            BrandInvitationService.accept_invitation(
                token=invitation.token,
                user=existing_user,
            )

    @patch("utils.notification_service.NotificationService.send_email")
    def test_register_and_accept_invitation(self, mock_email, brand_owner, brand):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="brandnew@example.com",
            role=BrandRoleChoices.ADMIN,
        )

        new_user, tokens = BrandInvitationService.register_and_accept_invitation(
            token=invitation.token,
            password="SecurePassword123!",
            first_name="Brand",
            last_name="New",
            handle="brandnew",
        )

        assert new_user.email == "brandnew@example.com"
        assert "access" in tokens
        assert BrandMember.objects.filter(
            brand=brand, user=new_user, role=BrandRoleChoices.ADMIN
        ).exists()
        invitation.refresh_from_db()
        assert invitation.status == InvitationStatusChoices.ACCEPTED

    @patch("utils.notification_service.NotificationService.send_email")
    def test_revoke_and_resend_invitation(self, mock_email, brand_owner, brand):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="revokeme@example.com",
        )

        # Revoke
        revoked = BrandInvitationService.revoke_invitation(
            user=brand_owner, brand_id=brand.id, invitation_id=invitation.id
        )
        assert revoked.status == InvitationStatusChoices.REVOKED

        # Resend
        resent = BrandInvitationService.resend_invitation(
            user=brand_owner, brand_id=brand.id, invitation_id=invitation.id
        )
        assert resent.status == InvitationStatusChoices.PENDING
        assert resent.token != invitation.token

    def test_member_role_update_and_removal(self, brand_owner, brand, existing_user):
        member = BrandMember.objects.create(
            brand=brand, user=existing_user, role=BrandRoleChoices.EDITOR
        )

        # Update role to admin
        updated = BrandInvitationService.update_member_role(
            user=brand_owner,
            brand_id=brand.id,
            member_id=member.id,
            new_role=BrandRoleChoices.ADMIN,
        )
        assert updated.role == BrandRoleChoices.ADMIN

        # Remove member
        BrandInvitationService.remove_member(
            user=brand_owner, brand_id=brand.id, member_id=member.id
        )
        assert not BrandMember.objects.filter(id=member.id).exists()


class TestBrandInvitationAPIEndpoints:
    @patch("utils.notification_service.NotificationService.send_email")
    def test_send_and_list_invitations_api(
        self, mock_email, api_client, brand_owner, brand
    ):
        api_client.force_authenticate(user=brand_owner)

        # Send invitation
        send_url = reverse("brand-invitations", kwargs={"brand_id": brand.id})
        response = api_client.post(
            send_url,
            {"email": "collab_api@example.com", "role": "editor"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["email"] == "collab_api@example.com"
        assert response.data["data"]["role"] == "editor"

        # List invitations
        list_response = api_client.get(send_url)
        assert list_response.status_code == status.HTTP_200_OK
        assert len(list_response.data["data"]) == 1

    @patch("utils.notification_service.NotificationService.send_email")
    def test_resend_and_revoke_invitation_api(
        self, mock_email, api_client, brand_owner, brand
    ):
        api_client.force_authenticate(user=brand_owner)
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="resend_api@example.com",
        )

        # Resend
        resend_url = reverse(
            "brand-invitation-resend",
            kwargs={"brand_id": brand.id, "invitation_id": invitation.id},
        )
        res_response = api_client.post(resend_url)
        assert res_response.status_code == status.HTTP_200_OK

        # Revoke
        revoke_url = reverse(
            "brand-invitation-revoke",
            kwargs={"brand_id": brand.id, "invitation_id": invitation.id},
        )
        del_response = api_client.delete(revoke_url)
        assert del_response.status_code == status.HTTP_200_OK

        # Revoking again should be idempotent and succeed
        del_again_response = api_client.delete(revoke_url)
        assert del_again_response.status_code == status.HTTP_200_OK

        # Listing invitations should not include the revoked invitation by default
        list_url = reverse("brand-invitations", kwargs={"brand_id": brand.id})
        list_res = api_client.get(list_url)
        assert list_res.status_code == status.HTTP_200_OK
        assert len(list_res.data["data"]) == 0

        # Listing invitations with ?status=all should include the revoked invitation
        list_all_res = api_client.get(f"{list_url}?status=all")
        assert list_all_res.status_code == status.HTTP_200_OK
        assert len(list_all_res.data["data"]) == 1
        assert list_all_res.data["data"][0]["status"] == InvitationStatusChoices.REVOKED

    @patch("utils.notification_service.NotificationService.send_email")
    def test_public_invitation_details_endpoint(
        self, mock_email, api_client, brand_owner, brand
    ):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="public_details@example.com",
            role=BrandRoleChoices.VIEWER,
        )

        detail_url = reverse("invitation-details", kwargs={"token": invitation.token})
        response = api_client.get(detail_url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["email"] == "public_details@example.com"
        assert data["brand_name"] == brand.name
        assert data["role"] == BrandRoleChoices.VIEWER
        assert data["user_exists"] is False
        assert data["is_expired"] is False

    @patch("utils.notification_service.NotificationService.send_email")
    def test_accept_invitation_authenticated_api(
        self, mock_email, api_client, brand_owner, brand, existing_user
    ):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email=existing_user.email,
            role=BrandRoleChoices.EDITOR,
        )

        api_client.force_authenticate(user=existing_user)
        accept_url = reverse("invitation-accept", kwargs={"token": invitation.token})
        response = api_client.post(accept_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["role"] == BrandRoleChoices.EDITOR

    @patch("utils.notification_service.NotificationService.send_email")
    def test_register_and_accept_invitation_api(
        self, mock_email, api_client, brand_owner, brand
    ):
        invitation = BrandInvitationService.send_invitation(
            inviter=brand_owner,
            brand_id=brand.id,
            email="register_accept@example.com",
            role=BrandRoleChoices.ADMIN,
        )

        reg_url = reverse(
            "invitation-register-accept", kwargs={"token": invitation.token}
        )
        response = api_client.post(
            reg_url,
            {
                "password": "Password123!",
                "first_name": "New",
                "last_name": "Collaborator",
                "handle": "newcollab1",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["user"]["email"] == "register_accept@example.com"
        assert "tokens" in response.data["data"]

    def test_members_list_update_delete_api(
        self, api_client, brand_owner, brand, existing_user
    ):
        member = BrandMember.objects.create(
            brand=brand, user=existing_user, role=BrandRoleChoices.VIEWER
        )

        api_client.force_authenticate(user=brand_owner)

        # List members
        members_url = reverse("brand-members", kwargs={"brand_id": brand.id})
        response = api_client.get(members_url)
        assert response.status_code == status.HTTP_200_OK
        # 2 members: owner + existing_user
        assert len(response.data["data"]) == 2

        # Update role
        member_detail_url = reverse(
            "brand-member-detail",
            kwargs={"brand_id": brand.id, "member_id": member.id},
        )
        patch_response = api_client.patch(
            member_detail_url,
            {"role": "editor"},
            format="json",
        )
        assert patch_response.status_code == status.HTTP_200_OK
        assert patch_response.data["data"]["role"] == "editor"

        # Delete member
        del_response = api_client.delete(member_detail_url)
        assert del_response.status_code == status.HTTP_200_OK
        assert not BrandMember.objects.filter(id=member.id).exists()
