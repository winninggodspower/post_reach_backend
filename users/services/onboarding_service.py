from django.db import transaction

from social_accounts.models import Brand
from utils.custom_logger import log_exceptions


class OnboardingService:
    @staticmethod
    @log_exceptions()
    def complete_onboarding(
        *,
        user,
        role,
        industry,
        posting_frequency,
        primary_platform,
        team_size,
    ):
        with transaction.atomic():
            user.role = role
            user.save(update_fields=["role"])

            brand, _ = Brand.objects.get_or_create(
                user=user,
                is_default=True,
                defaults={
                    "name": user.handle or user.get_full_name().strip() or user.email.split("@")[0],
                },
            )

            brand.industry = industry
            brand.posting_frequency = posting_frequency
            brand.primary_platform = primary_platform
            brand.team_size = team_size
            brand.save(
                update_fields=[
                    "industry",
                    "posting_frequency",
                    "primary_platform",
                    "team_size",
                ]
            )

        return user, brand
