from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from social_accounts.models import SocialAccount


@shared_task
def refresh_expiring_tokens():
    soon = timezone.now() + timedelta(minutes=30)

    # Get tokens that will expire in the next 10 minutes
    expiring_accounts = SocialAccount.objects.filter(expires_at__lte=soon)

    refreshed = 0
    for account in expiring_accounts:
        if account.refresh_access_token():
            refreshed += 1

    return f"Refreshed {refreshed} tokens"
