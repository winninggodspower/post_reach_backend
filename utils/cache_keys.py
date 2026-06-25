"""
Central namespace for all cache key generation across the project.

All cache key functions live here so there is a single source of truth,
avoiding key collisions and making cache keys easy to discover.
"""


class CacheKeys:
    """Central namespace for all cache key generation."""

    # ------------------------------------------------------------------
    # Password Reset
    # ------------------------------------------------------------------
    @classmethod
    def pw_reset_otp(cls, email: str) -> str:
        """Cache key for storing a password reset OTP for an email."""
        return f"pw_reset_otp:{email.lower()}"

    @classmethod
    def pw_reset_rate_limit(cls, email: str) -> str:
        """Cache key for rate-limiting password reset requests per email."""
        return f"pw_reset_rate_limit:{email.lower()}"

    @classmethod
    def pw_reset_token(cls, token: str) -> str:
        """Cache key for storing a password reset authorization token."""
        return f"pw_reset_token:{token}"

    # ------------------------------------------------------------------
    # Social Account OAuth
    # ------------------------------------------------------------------
    @classmethod
    def youtube_oauth_state(cls, user_id: int) -> str:
        """Cache key for storing YouTube OAuth state for a user."""
        return f"youtube_oauth_state:{user_id}"

    @classmethod
    def facebook_oauth_state(cls, user_id: int) -> str:
        """Cache key for storing Facebook OAuth state for a user."""
        return f"facebook_oauth_state:{user_id}"

    @classmethod
    def instagram_oauth_state(cls, user_id: int) -> str:
        """Cache key for storing Instagram OAuth state for a user."""
        return f"instagram_oauth_state:{user_id}"

    @classmethod
    def tiktok_oauth_state(cls, user_id: int) -> str:
        """Cache key for storing TikTok OAuth state for a user."""
        return f"tiktok_oauth_state:{user_id}"

    @classmethod
    def tiktok_code_verifier(cls, user_id: int) -> str:
        """Cache key for storing TikTok PKCE code verifier for a user."""
        return f"tiktok_code_verifier:{user_id}"

    @classmethod
    def linkedin_oauth_state(cls, user_id: int) -> str:
        """Cache key for storing LinkedIn OAuth state for a user."""
        return f"linkedin_oauth_state:{user_id}"
