from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from social_accounts.models import Brand


@receiver(post_save, sender=User)
def create_default_brand(sender, instance, created, **kwargs):
    if created:
        brand_name = (
            instance.handle
            or instance.get_full_name().strip()
            or instance.email.split("@")[0]
        )

        Brand.objects.get_or_create(
            user=instance,
            is_default=True,
            defaults={
                "name": brand_name,
            },
        )
