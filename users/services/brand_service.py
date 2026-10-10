from django.db import transaction
from django.db.models import Q

from users.enums import BrandRoleChoices
from users.models import Brand, BrandMember, User


class BrandService:
    @staticmethod
    def get_default_brand(user: User) -> Brand:
        """
        Return the user's default brand.

        Raises ValueError if no default brand is set.
        """
        brand = Brand.objects.filter(user=user, is_default=True).first()
        if not brand:
            raise ValueError("No default brand found. Please create a brand first.")
        return brand

    @staticmethod
    def get_brand_by_id(user: User, brand_id) -> Brand:
        brand = (
            Brand.objects.filter(
                Q(id=brand_id) & (Q(user=user) | Q(members__user=user))
            )
            .distinct()
            .first()
        )
        if not brand:
            raise ValueError(
                "Brand not found or you don't have permission to access it."
            )
        return brand

    @staticmethod
    def get_accessible_brands(user: User):
        """
        Return all brands the user has access to (owned or collaborated).
        """
        return (
            Brand.objects.filter(Q(user=user) | Q(members__user=user))
            .distinct()
            .order_by("-is_default", "name")
        )

    @staticmethod
    def create_brand(user: User, validated_data: dict) -> Brand:
        # Prevent users from creating a second default brand
        if validated_data.get("is_default", False):
            validated_data["is_default"] = False

        if not Brand.objects.filter(user=user).exists():
            validated_data["is_default"] = True

        with transaction.atomic():
            brand = Brand.objects.create(user=user, **validated_data)
            BrandMember.objects.create(
                brand=brand,
                user=user,
                role=BrandRoleChoices.OWNER,
            )
            return brand
