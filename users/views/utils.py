from django.db.models import Prefetch

from users.models import Brand, User
from users.serializers import UserSerializer
from users.services import UserService


def _prefetch_user_for_serialization(user):
    """Prefetch brands and their social_accounts to avoid N+1 queries."""
    return User.objects.prefetch_related(
        Prefetch("brands", queryset=Brand.objects.prefetch_related("social_accounts"))
    ).get(pk=user.pk)


def get_auth_response_data(user):
    return {
        "user": UserSerializer(_prefetch_user_for_serialization(user)).data,
        "tokens": UserService.get_auth_tokens(user),
    }


def get_onboarding_response_data(user, brand):
    # UserSerializer now includes `brand` nested inside, so we only need the user.
    return {
        "user": UserSerializer(_prefetch_user_for_serialization(user)).data,
    }
