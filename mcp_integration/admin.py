from django.contrib import admin
from oauth2_provider.admin import AccessTokenAdmin, RefreshTokenAdmin
from oauth2_provider.models import get_access_token_model, get_refresh_token_model

AccessToken = get_access_token_model()
RefreshToken = get_refresh_token_model()


class DeletableAccessTokenAdmin(AccessTokenAdmin):
    """
    Allow staff/superusers with delete permissions to delete AccessToken records
    (and cascade-delete Applications or Users in Django Admin).
    """

    def has_delete_permission(self, request, obj=None):
        return admin.ModelAdmin.has_delete_permission(self, request, obj)


class DeletableRefreshTokenAdmin(RefreshTokenAdmin):
    """
    Allow staff/superusers with delete permissions to delete RefreshToken records
    (and cascade-delete Applications or Users in Django Admin).
    """

    def has_delete_permission(self, request, obj=None):
        return admin.ModelAdmin.has_delete_permission(self, request, obj)


if admin.site.is_registered(AccessToken):
    admin.site.unregister(AccessToken)
admin.site.register(AccessToken, DeletableAccessTokenAdmin)

if admin.site.is_registered(RefreshToken):
    admin.site.unregister(RefreshToken)
admin.site.register(RefreshToken, DeletableRefreshTokenAdmin)
