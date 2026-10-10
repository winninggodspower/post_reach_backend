import pytest
from django.urls import reverse

from users.models import Brand, User
from users.serializers import UserSerializer
from users.services.brand_service import BrandService
from users.services.user_service import UserService


class TestUserSerializerBrands:
    def test_single_default_brand_in_brands_list(self, db, user, brand):
        serializer = UserSerializer(user)
        data = serializer.data

        assert "brand" in data
        assert "brands" in data
        assert len(data["brands"]) == 1

        brand_item = data["brands"][0]
        assert str(brand_item["id"]) == str(brand.id)
        assert brand_item["name"] == brand.name
        assert brand_item["is_default"] is True
        assert brand_item["is_active"] is True
        assert brand_item["role"] == "owner"

    def test_multiple_brands_active_flag(self, db, user, brand):
        second_brand = BrandService.create_brand(
            user=user,
            validated_data={"name": "Second Brand"},
        )

        # By default, brand is active (is_default)
        data = UserSerializer(user).data
        assert len(data["brands"]) == 2

        active_items = [b for b in data["brands"] if b["is_active"]]
        inactive_items = [b for b in data["brands"] if not b["is_active"]]

        assert len(active_items) == 1
        assert str(active_items[0]["id"]) == str(brand.id)
        assert len(inactive_items) == 1
        assert str(inactive_items[0]["id"]) == str(second_brand.id)

        # Switch active brand to second_brand
        UserService.set_active_brand(user, second_brand.id)
        user.refresh_from_db()

        new_data = UserSerializer(user).data
        active_items = [b for b in new_data["brands"] if b["is_active"]]
        inactive_items = [b for b in new_data["brands"] if not b["is_active"]]

        assert len(active_items) == 1
        assert str(active_items[0]["id"]) == str(second_brand.id)
        assert len(inactive_items) == 1
        assert str(inactive_items[0]["id"]) == str(brand.id)

    def test_current_user_me_endpoint_returns_brands(
        self, db, authenticated_client, user, brand
    ):
        second_brand = BrandService.create_brand(
            user=user,
            validated_data={"name": "Client Brand"},
        )

        response = authenticated_client.get(reverse("current-user"))
        assert response.status_code == 200
        user_data = response.data["data"]

        assert "brand" in user_data
        assert "brands" in user_data
        assert len(user_data["brands"]) == 2

        ids = {b["id"] for b in user_data["brands"]}
        assert str(brand.id) in ids
        assert str(second_brand.id) in ids
