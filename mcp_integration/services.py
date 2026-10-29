from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from oauth2_provider.cimd import SafeMetadataFetcher
from oauth2_provider.models import AccessToken, Application, RefreshToken, clear_expired

from users.models import Brand, User
from users.services.brand_service import BrandService
from users.services.user_service import UserService


class MCPContextService:
    """Resolves authenticated user, OAuth scopes, and target brand for MCP tool calls."""

    @staticmethod
    def get_user_and_scopes(request) -> tuple[User, set[str]]:
        if (
            request is None
            or not getattr(request, "user", None)
            or not request.user.is_authenticated
        ):
            raise PermissionError("Authentication is required to invoke MCP tools.")

        token = getattr(request, "auth", None) or getattr(request, "access_token", None)
        scopes: set[str] = set()
        if token is not None and getattr(token, "scope", None):
            scopes = set(token.scope.split())
        return request.user, scopes

    @classmethod
    def require_scope(cls, request, required_scope: str) -> User:
        user, scopes = cls.get_user_and_scopes(request)
        if required_scope and required_scope not in scopes:
            raise PermissionError(
                f"Insufficient OAuth scope: '{required_scope}' is required for this tool."
            )
        return user

    @classmethod
    def resolve_brand(
        cls, request, *, required_scope: str, brand_id: str | None = None
    ) -> tuple[User, Brand]:
        user = cls.require_scope(request, required_scope)
        if brand_id:
            brand = BrandService.get_brand_by_id(user, brand_id)
        else:
            brand = UserService.get_active_brand(user)
            if not brand:
                raise ValueError(
                    "No active brand found. Please create or select a brand first."
                )
        return user, brand


class OAuthConnectionService:
    """Manage a user's authorized OAuth / MCP client connections."""

    @staticmethod
    def list_connections(user: User) -> list[dict]:
        now = timezone.now()
        tokens = (
            AccessToken.objects.filter(
                user=user,
                expires__gt=now,
                application__isnull=False,
            )
            .select_related("application")
            .order_by("-created")
        )

        by_app: dict[int, dict] = {}
        for tok in tokens:
            app = tok.application
            if app.id not in by_app:
                by_app[app.id] = {
                    "client_id": app.client_id,
                    "client_name": app.name or app.client_id,
                    "scopes": sorted(set(tok.scope.split())) if tok.scope else [],
                    "connected_at": tok.created,
                    "expires_at": tok.expires,
                }
            else:
                existing_scopes = set(by_app[app.id]["scopes"])
                if tok.scope:
                    existing_scopes.update(tok.scope.split())
                by_app[app.id]["scopes"] = sorted(existing_scopes)
                if tok.created < by_app[app.id]["connected_at"]:
                    by_app[app.id]["connected_at"] = tok.created
                if tok.expires > by_app[app.id]["expires_at"]:
                    by_app[app.id]["expires_at"] = tok.expires

        return list(by_app.values())

    @staticmethod
    def revoke_connection(user: User, client_id: str) -> int:
        app = Application.objects.filter(client_id=client_id).first()
        if not app:
            raise ValueError("Connected application not found.")

        with transaction.atomic():
            refresh_tokens = RefreshToken.objects.filter(
                user=user, application=app, revoked__isnull=True
            )
            for rt in refresh_tokens:
                rt.revoke()
            deleted_count, _ = AccessToken.objects.filter(
                user=user, application=app
            ).delete()

        return deleted_count

    @staticmethod
    def cleanup_expired_and_stale_clients(stale_days: int = 90) -> dict:
        """
        Clear expired OAuth tokens/grants and prune dynamically registered clients
        that have no tokens or grants and haven't been updated in `stale_days`.
        """
        clear_expired()
        cutoff = timezone.now() - timedelta(days=stale_days)
        stale_apps = (
            Application.objects.filter(
                registration_source=Application.RegistrationSource.DCR,
                updated__lt=cutoff,
            )
            .exclude(accesstoken__user__isnull=False)
            .exclude(refreshtoken__isnull=False)
            .exclude(grant__isnull=False)
            .distinct()
        )
        deleted_apps, _ = stale_apps.delete()
        return {"deleted_dcr_clients": deleted_apps}


class PostGleeCIMDMetadataFetcher(SafeMetadataFetcher):
    """
    Normalizes `grant_types` on fetched CIMD documents (such as Claude's
    `https://claude.ai/oauth/mcp-oauth-client-metadata`, which declares
    `urn:ietf:params:oauth:grant-type:jwt-bearer` alongside `authorization_code`)
    so django-oauth-toolkit's single-grant-type check succeeds.
    """

    def fetch(self, client_id: str):
        metadata, max_age = super().fetch(client_id)
        grant_types = metadata.get("grant_types")
        if isinstance(grant_types, list) and "authorization_code" in grant_types:
            metadata["grant_types"] = [
                g for g in grant_types if g in ("authorization_code", "refresh_token")
            ]
        return metadata, max_age
