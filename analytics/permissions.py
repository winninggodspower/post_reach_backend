from rest_framework.permissions import BasePermission


class IsSuperAdminUser(BasePermission):
    """
    Permission class that grants access only to authenticated superusers.
    """

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_superuser
        )
