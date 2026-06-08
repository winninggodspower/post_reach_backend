"""
Cache key namespaces for social_accounts app.
Each namespace has a function that generates the full cache key.
"""


def youtube_oauth_state(user_id):
    """Cache key for storing YouTube OAuth state for a user."""
    return f"youtube_oauth_state:{user_id}"


def facebook_oauth_state(user_id):
    """Cache key for storing Facebook OAuth state for a user."""
    return f"facebook_oauth_state:{user_id}"


def instagram_oauth_state(user_id):
    """Cache key for storing Instagram OAuth state for a user."""
    return f"instagram_oauth_state:{user_id}"
