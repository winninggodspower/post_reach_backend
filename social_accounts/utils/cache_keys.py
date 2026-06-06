"""
Cache key namespaces for social_accounts app.
Each namespace has a function that generates the full cache key.
"""


def youtube_oauth_state(user_id):
    """Cache key for storing YouTube OAuth state for a user."""
    return f"youtube_oauth_state:{user_id}"
