from django.core.management.base import BaseCommand

from subscriptions.services import SubscriptionService


class Command(BaseCommand):
    help = (
        "Seeds or updates default Postglee subscription plans (Free, Pro, Enterprise)"
    )

    def handle(self, *args, **options):
        SubscriptionService.seed_default_plans()
        self.stdout.write(self.style.SUCCESS("Successfully seeded subscription plans."))
