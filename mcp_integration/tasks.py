from celery import shared_task

from mcp_integration.services import OAuthConnectionService


@shared_task
def cleanup_oauth_tokens_and_dcr_clients():
    """Periodic task to prune expired OAuth tokens/grants and unused DCR clients."""
    return OAuthConnectionService.cleanup_expired_and_stale_clients()

