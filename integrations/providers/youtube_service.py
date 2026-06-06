import uuid

import google_auth_oauthlib
import googleapiclient.discovery
import oauthlib.oauth2.rfc6749.errors
from django.conf import settings
from django.core.cache import cache
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from integrations.providers.base import SocialAccountService
from social_accounts.utils.cache_keys import youtube_oauth_state
from utils.custom_logger import CustomLogger

OAUTH_STATE_TTL = 600  # 10 minutes


class YoutubeService(SocialAccountService):
    CLIENT_ID = settings.GOOGLE_CLIENT_ID
    CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET

    REQUIRED_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    @classmethod
    def generate_auth_url(cls, user_id, redirect_uri):
        """
        Generates a YouTube OAuth authorization URL with CSRF state protection.
        Stores the state in cache for later verification.
        """
        state = str(uuid.uuid4())
        cache.set(youtube_oauth_state(user_id), state, OAUTH_STATE_TTL)

        client_config = {
            "web": {
                "client_id": cls.CLIENT_ID,
                "client_secret": cls.CLIENT_SECRET,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            client_config,
            scopes=cls.REQUIRED_SCOPES,
            redirect_uri=redirect_uri,
        )

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",
        )

        return authorization_url

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
    def connect_account(cls, *, user, auth_code, redirect_uri, state=None, brand=None):
        """
        Complete the YouTube OAuth connection flow:
        1. Verify the OAuth state (CSRF protection)
        2. Resolve the brand
        3. Exchange the auth code for tokens
        4. Save the social account

        Returns the created/updated SocialAccount instance.
        Raises ValueError or PermissionError on failure.
        """
        from social_accounts.models import SocialAccount

        # 1. State verification
        if state:
            cached_state = cache.get(youtube_oauth_state(user.id))
            if not cached_state or state != cached_state:
                raise ValueError("Invalid state parameter. Possible CSRF attack.")
            cache.delete(youtube_oauth_state(user.id))

        # 2. Brand resolution
        resolved_brand = cls._resolve_brand(user, brand)

        # 3. Exchange code for token
        credentials, missing_scopes = cls.exchange_code_for_token(
            auth_code=auth_code,
            google_auth_redirect_uri=redirect_uri,
        )

        if missing_scopes:
            raise ValueError(
                f"Missing required permissions: {', '.join(sorted(missing_scopes))}"
            )

        # 4. Save account
        account, _ = SocialAccount.objects.update_or_create(
            brand=resolved_brand,
            platform="youtube",
            defaults={
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expires_at": credentials.expiry,
                "scope": " ".join(credentials.scopes),
            },
        )

        return account

    @classmethod
    def exchange_code_for_token(cls, auth_code, google_auth_redirect_uri):
        try:
            client_config = {
                "web": {
                    "client_id": cls.CLIENT_ID,
                    "client_secret": cls.CLIENT_SECRET,
                    "redirect_uris": [google_auth_redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }

            flow = google_auth_oauthlib.flow.Flow.from_client_config(
                client_config,
                scopes=cls.REQUIRED_SCOPES,
                redirect_uri=google_auth_redirect_uri,
            )

            flow.fetch_token(code=auth_code)

            credentials = flow.credentials

            missing_scopes = set(cls.REQUIRED_SCOPES) - set(credentials.scopes)

            return credentials, missing_scopes
        except oauthlib.oauth2.rfc6749.errors.InvalidGrantError:
            CustomLogger.exception("YouTube authorization code exchange failed due to invalid grant", extra={"operation": "exchange_code_for_token", "redirect_uri": google_auth_redirect_uri})
            raise ValueError("Authorization code has expired or is invalid")
        except Exception as e:
            CustomLogger.exception("Unexpected YouTube token exchange failure", extra={"operation": "exchange_code_for_token", "redirect_uri": google_auth_redirect_uri})
            raise Exception(f"Error exchanging code for token: {str(e)}")

    @classmethod
    def refresh_access_token(cls, refresh_token):
        credentials = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cls.CLIENT_ID,
            client_secret=cls.CLIENT_SECRET,
            scopes=cls.REQUIRED_SCOPES,
        )

        request = Request()
        credentials.refresh(request)

        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_in": credentials.expiry,
        }

    @classmethod
    def get_youtube_client(cls, access_token):
        credentials = Credentials(
            token=access_token,
            client_id=cls.CLIENT_ID,
            client_secret=cls.CLIENT_SECRET,
            scopes=cls.REQUIRED_SCOPES,
        )
        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
