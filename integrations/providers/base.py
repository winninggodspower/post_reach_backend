from abc import ABC, abstractmethod
from utils.http import BaseHTTPClient

class SocialAccountService(BaseHTTPClient, ABC):
    BASE_URL = ""

    def __init__(self):
        super().__init__(base_url=self.BASE_URL)

    @classmethod
    def _resolve_brand(cls, user, brand_from_request):
        """
        Resolve the brand to use for the connection.
        If a brand is provided, verify ownership and return it.
        If no brand is provided, return the user's default brand.
        """
        from users.models import Brand

        if brand_from_request is not None:
            if brand_from_request.user != user:
                raise PermissionError("You do not have permission to access this brand.")
            return brand_from_request

        default_brand = Brand.objects.filter(user=user, is_default=True).first()
        if default_brand is None:
            raise ValueError("No default brand found. Please create a brand or specify one.")
        return default_brand

    @classmethod
    @abstractmethod
    def refresh_access_token(self, refresh_token: str) -> list[str]:
        """
        Refresh the access token using the refresh token.
        :param refresh_token: The refresh token to authenticate the request.
        :return: A new access token, refresh_token and expires_at.
        """
        raise NotImplementedError("Subclasses must implement this method.")
