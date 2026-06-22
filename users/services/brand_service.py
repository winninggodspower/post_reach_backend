from users.models import Brand, User


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
