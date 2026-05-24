import google_auth_oauthlib
import googleapiclient.discovery
import oauthlib.oauth2.rfc6749.errors
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from integrations.providers.base import SocialAccountService



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
            raise ValueError("Authorization code has expired or is invalid")
        except Exception as e:
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
