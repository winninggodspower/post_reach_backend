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

    @staticmethod
    def get_brand_by_id(user: User, brand_id) -> Brand:
        brand = Brand.objects.filter(id=brand_id, user=user).first()
        if not brand:
            raise ValueError("Brand not found or you don't have permission to access it.")
        return brand

    @staticmethod
    def create_brand(user: User, validated_data: dict) -> Brand:
        # Prevent users from creating a second default brand
        if validated_data.get('is_default', False):
            # For simplicity, we just force it to False here if a default already exists,
            # or handle it differently. But we should just force it to False for additional brands.
            validated_data['is_default'] = False

        if not Brand.objects.filter(user=user).exists():
            validated_data['is_default'] = True
            
        return Brand.objects.create(user=user, **validated_data)
