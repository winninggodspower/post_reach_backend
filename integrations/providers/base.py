from abc import ABC, abstractmethod


class SocialAccountService(ABC):
    @classmethod
    @abstractmethod
    def refresh_access_token(self, refresh_token: str) -> list[str]:
        """
        Refresh the access token using the refresh token.
        :param refresh_token: The refresh token to authenticate the request.
        :return: A new access token, refresh_token and expires_at.
        """
        raise NotImplementedError("Subclasses must implement this method.")
