from typing import List, Set

from social_accounts.models import SocialAccount
from users.models import Brand


class SocialAccountValidationService:
    @staticmethod
    def get_connected_platforms(brand: Brand) -> Set[str]:
        """Return the set of platform values connected to the brand."""
        return set(
            SocialAccount.objects.filter(brand=brand)
            .values_list("platform", flat=True)
        )

    @staticmethod
    def ensure_platforms_connected(brand: Brand, platforms: List[str]) -> None:
        """
        Validate that every requested platform has a connected SocialAccount.

        Raises ValueError listing any unconnected platforms.
        """
        connected = SocialAccountValidationService.get_connected_platforms(brand)
        missing = [p for p in platforms if p not in connected]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(
                f"No connected account(s) found for: {joined}. "
                "Please connect your account(s) first."
            )