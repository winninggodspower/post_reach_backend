from django.contrib import admin

from content.models import ContentPostPlatform


# Register your models here.
class ContentPostPlatformAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "content_post",
        "platform",
        "status",
        "platform_post_id",
        "created_at",
        "updated_at",
    )
    list_filter = ("platform", "status", "created_at", "updated_at")
    search_fields = ("content_post__title", "platform_post_id")


admin.site.register(ContentPostPlatform, ContentPostPlatformAdmin)
