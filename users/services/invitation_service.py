import secrets
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from users.enums import BrandRoleChoices, InvitationStatusChoices
from users.models import Brand, BrandInvitation, BrandMember, User
from users.services.brand_service import BrandService
from users.services.user_service import UserService
from utils.custom_logger import log_exceptions
from utils.frontend_urls import FrontendUrls
from utils.notification_service import NotificationService

INVITATION_EXPIRY_DAYS = 7


class BrandInvitationService:
    """Domain service managing brand invitations and collaborator memberships."""

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def get_user_role_in_brand(cls, user: User, brand: Brand) -> str | None:
        """
        Returns the user's role in the brand.
        If user is the brand owner, returns OWNER.
        Otherwise checks BrandMember table. Returns None if not a member.
        """
        if brand.user == user:
            return str(BrandRoleChoices.OWNER)
        membership = BrandMember.objects.filter(brand=brand, user=user).first()
        return membership.role if membership else None

    @classmethod
    def can_manage_members(cls, user: User, brand: Brand) -> bool:
        """Only brand Owner and Admins can manage members and invitations."""
        role = cls.get_user_role_in_brand(user, brand)
        return role in (BrandRoleChoices.OWNER, BrandRoleChoices.ADMIN)

    @classmethod
    @log_exceptions()
    def send_invitation(
        cls,
        *,
        inviter: User,
        brand_id: UUID | str,
        email: str,
        role: str = BrandRoleChoices.EDITOR,
    ) -> BrandInvitation:
        brand = BrandService.get_brand_by_id(inviter, brand_id)
        if not cls.can_manage_members(inviter, brand):
            raise ValueError(
                "You do not have permission to invite members to this brand."
            )

        if role == BrandRoleChoices.OWNER:
            raise ValueError("Cannot invite a collaborator as Owner.")

        if role not in BrandRoleChoices.values:
            raise ValueError(f"Invalid role: {role}.")

        normalized_email = email.strip().lower()

        # Prevent inviting the brand owner
        if brand.user.email.lower() == normalized_email:
            raise ValueError("This user is already the owner of the brand.")

        # Check if already a member
        if BrandMember.objects.filter(
            brand=brand, user__email__iexact=normalized_email
        ).exists():
            raise ValueError(
                f"A user with email '{normalized_email}' is already a member of this brand."
            )

        expires_at = timezone.now() + timedelta(days=INVITATION_EXPIRY_DAYS)
        token = cls._generate_token()

        with transaction.atomic():
            # Check for existing pending invitation to reuse/update
            existing_invite = BrandInvitation.objects.filter(
                brand=brand,
                email__iexact=normalized_email,
                status=InvitationStatusChoices.PENDING,
            ).first()

            if existing_invite:
                existing_invite.role = role
                existing_invite.token = token
                existing_invite.expires_at = expires_at
                existing_invite.invited_by = inviter
                existing_invite.save(
                    update_fields=[
                        "role",
                        "token",
                        "expires_at",
                        "invited_by",
                        "updated_at",
                    ]
                )
                invitation = existing_invite
            else:
                invitation = BrandInvitation.objects.create(
                    brand=brand,
                    email=normalized_email,
                    role=role,
                    invited_by=inviter,
                    token=token,
                    status=InvitationStatusChoices.PENDING,
                    expires_at=expires_at,
                )

        # Dispatch invitation email
        accept_url = FrontendUrls.invitation_accept(invitation.token)
        inviter_name = inviter.get_full_name() or inviter.handle or inviter.email
        role_label = dict(BrandRoleChoices.choices).get(role, role.capitalize())

        NotificationService.send_email(
            to_email=normalized_email,
            subject=f"You've been invited to join {brand.name} on PostGlee",
            template_name="emails/brand_invitation.html",
            context={
                "inviter_name": inviter_name,
                "inviter_email": inviter.email,
                "brand_name": brand.name,
                "role_label": role_label,
                "accept_url": accept_url,
            },
        )

        return invitation

    @classmethod
    def get_invitation_by_token(cls, token: str) -> BrandInvitation:
        invitation = (
            BrandInvitation.objects.select_related("brand", "invited_by")
            .filter(token=token)
            .first()
        )
        if not invitation:
            raise ValueError("Invalid invitation link.")

        if (
            invitation.status == InvitationStatusChoices.PENDING
            and invitation.expires_at <= timezone.now()
        ):
            invitation.status = InvitationStatusChoices.EXPIRED
            invitation.save(update_fields=["status", "updated_at"])
            raise ValueError("This invitation has expired.")

        if invitation.status != InvitationStatusChoices.PENDING:
            raise ValueError(
                f"This invitation has already been {invitation.status.lower()}."
            )

        return invitation

    @classmethod
    @log_exceptions()
    def accept_invitation(cls, *, token: str, user: User) -> tuple[BrandMember, Brand]:
        invitation = cls.get_invitation_by_token(token)
        brand = invitation.brand

        if user.email.lower() != invitation.email.lower():
            raise ValueError(
                f"This invitation was sent to '{invitation.email}'. "
                f"You are currently signed in as '{user.email}'."
            )

        with transaction.atomic():
            member, created = BrandMember.objects.get_or_create(
                brand=brand,
                user=user,
                defaults={"role": invitation.role},
            )
            if not created and member.role != invitation.role:
                member.role = invitation.role
                member.save(update_fields=["role", "updated_at"])

            invitation.status = InvitationStatusChoices.ACCEPTED
            invitation.save(update_fields=["status", "updated_at"])

            # Set as active brand if user has none
            if not user.active_brand:
                user.active_brand = brand
                user.save(update_fields=["active_brand"])

        return member, brand

    @classmethod
    @log_exceptions()
    def register_and_accept_invitation(
        cls,
        *,
        token: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
        handle: str | None = None,
    ) -> tuple[User, dict[str, str]]:
        invitation = cls.get_invitation_by_token(token)
        email = invitation.email

        with transaction.atomic():
            user = UserService.register_with_password(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                handle=handle,
            )
            cls.accept_invitation(token=token, user=user)
            tokens = UserService.get_auth_tokens(user)

        return user, tokens

    @classmethod
    def revoke_invitation(
        cls, *, user: User, brand_id: UUID | str, invitation_id: UUID | str
    ) -> BrandInvitation:
        brand = BrandService.get_brand_by_id(user, brand_id)
        if not cls.can_manage_members(user, brand):
            raise ValueError(
                "You do not have permission to revoke invitations for this brand."
            )

        invitation = BrandInvitation.objects.filter(
            id=invitation_id, brand=brand
        ).first()
        if not invitation:
            raise ValueError("Invitation not found.")

        if invitation.status != InvitationStatusChoices.PENDING:
            raise ValueError(
                f"Cannot revoke an invitation that is already {invitation.status.lower()}."
            )

        invitation.status = InvitationStatusChoices.REVOKED
        invitation.save(update_fields=["status", "updated_at"])
        return invitation

    @classmethod
    def resend_invitation(
        cls, *, user: User, brand_id: UUID | str, invitation_id: UUID | str
    ) -> BrandInvitation:
        brand = BrandService.get_brand_by_id(user, brand_id)
        if not cls.can_manage_members(user, brand):
            raise ValueError(
                "You do not have permission to resend invitations for this brand."
            )

        invitation = BrandInvitation.objects.filter(
            id=invitation_id, brand=brand
        ).first()
        if not invitation:
            raise ValueError("Invitation not found.")

        # Renew token & expiration
        invitation.token = cls._generate_token()
        invitation.expires_at = timezone.now() + timedelta(days=INVITATION_EXPIRY_DAYS)
        invitation.status = InvitationStatusChoices.PENDING
        invitation.save(update_fields=["token", "expires_at", "status", "updated_at"])

        accept_url = FrontendUrls.invitation_accept(invitation.token)
        inviter_name = user.get_full_name() or user.handle or user.email
        role_label = dict(BrandRoleChoices.choices).get(
            invitation.role, invitation.role.capitalize()
        )

        NotificationService.send_email(
            to_email=invitation.email,
            subject=f"Reminder: You've been invited to join {brand.name} on PostGlee",
            template_name="emails/brand_invitation.html",
            context={
                "inviter_name": inviter_name,
                "inviter_email": user.email,
                "brand_name": brand.name,
                "role_label": role_label,
                "accept_url": accept_url,
            },
        )
        return invitation

    @classmethod
    def list_brand_invitations(
        cls, *, user: User, brand_id: UUID | str
    ) -> QuerySet[BrandInvitation]:
        brand = BrandService.get_brand_by_id(user, brand_id)
        if not cls.can_manage_members(user, brand):
            raise ValueError(
                "You do not have permission to view invitations for this brand."
            )

        return (
            BrandInvitation.objects.filter(brand=brand)
            .select_related("invited_by")
            .order_by("-created_at")
        )

    @classmethod
    def list_brand_members(
        cls, *, user: User, brand_id: UUID | str
    ) -> QuerySet[BrandMember]:
        brand = BrandService.get_brand_by_id(user, brand_id)
        role = cls.get_user_role_in_brand(user, brand)
        if not role:
            raise ValueError(
                "You do not have permission to view members of this brand."
            )

        return (
            BrandMember.objects.filter(brand=brand)
            .select_related("user")
            .order_by("-created_at")
        )

    @classmethod
    def update_member_role(
        cls, *, user: User, brand_id: UUID | str, member_id: UUID | str, new_role: str
    ) -> BrandMember:
        brand = BrandService.get_brand_by_id(user, brand_id)
        if not cls.can_manage_members(user, brand):
            raise ValueError("You do not have permission to manage member roles.")

        if new_role not in (
            BrandRoleChoices.ADMIN,
            BrandRoleChoices.EDITOR,
            BrandRoleChoices.VIEWER,
        ):
            raise ValueError(f"Invalid member role: {new_role}.")

        member = (
            BrandMember.objects.filter(id=member_id, brand=brand)
            .select_related("user")
            .first()
        )
        if not member:
            raise ValueError("Member not found.")

        if member.role == BrandRoleChoices.OWNER:
            raise ValueError("Cannot change the role of the brand owner.")

        # Admins cannot change other Admins, only Owner can
        user_role = cls.get_user_role_in_brand(user, brand)
        if (
            user_role == BrandRoleChoices.ADMIN
            and member.role == BrandRoleChoices.ADMIN
        ):
            raise ValueError("Only the brand owner can modify admin roles.")

        member.role = new_role
        member.save(update_fields=["role", "updated_at"])
        return member

    @classmethod
    def remove_member(
        cls, *, user: User, brand_id: UUID | str, member_id: UUID | str
    ) -> None:
        brand = BrandService.get_brand_by_id(user, brand_id)
        member = BrandMember.objects.filter(id=member_id, brand=brand).first()
        if not member:
            raise ValueError("Member not found.")

        if member.role == BrandRoleChoices.OWNER or member.user == brand.user:
            raise ValueError("Cannot remove the brand owner from the brand.")

        # Self-removal (leaving brand) or admin/owner removal
        is_self = member.user == user
        can_manage = cls.can_manage_members(user, brand)

        if not (is_self or can_manage):
            raise ValueError("You do not have permission to remove this member.")

        # Admins cannot remove other Admins, only Owner can
        user_role = cls.get_user_role_in_brand(user, brand)
        if (
            not is_self
            and user_role == BrandRoleChoices.ADMIN
            and member.role == BrandRoleChoices.ADMIN
        ):
            raise ValueError("Only the brand owner can remove an admin.")

        with transaction.atomic():
            # If this brand was the removed user's active brand, reset it to their default brand
            if member.user.active_brand == brand:
                default_brand = Brand.objects.filter(
                    user=member.user, is_default=True
                ).first()
                member.user.active_brand = default_brand
                member.user.save(update_fields=["active_brand"])

            member.delete()
