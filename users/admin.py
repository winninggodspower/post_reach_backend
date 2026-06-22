from django.contrib import admin

from .models import Brand, User


# Register your models here.
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "first_name",
        "last_name",
        "handle",
        "role",
        "is_staff",
        "is_active",
        "date_joined",
        "last_login",
    )
    search_fields = ("email", "first_name", "last_name", "handle")
    list_filter = ("role", "is_staff", "is_active")


class BrandAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "name",
        "industry",
        "posting_frequency",
        "primary_platform",
        "team_size",
        "is_default",
        "created_at",
        "updated_at",
    )
    search_fields = ("user__email", "name", "industry", "primary_platform")
    list_filter = ("industry", "primary_platform", "is_default")


admin.site.register(User, UserAdmin)
admin.site.register(Brand, BrandAdmin)
