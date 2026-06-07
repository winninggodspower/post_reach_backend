from django.contrib import admin
from .models import SocialAccount

# Register your models here.
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "brand", "platform", "account_name", "external_id", "created_at", "updated_at")
    search_fields = ("brand__name", "platform", "account_name", "external_id")
    list_filter = ("platform",)

admin.site.register(SocialAccount ,SocialAccountAdmin)