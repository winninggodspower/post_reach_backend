from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


@receiver(post_save, sender=User)
def create_default_subscription(sender, instance, created, **kwargs):
    if created:
        from subscriptions.services.subscription_service import SubscriptionService

        try:
            SubscriptionService.get_or_create_default_subscription(instance)
        except Exception:
            # Avoid breaking user creation during initial setup or unmigrated tests
            pass
