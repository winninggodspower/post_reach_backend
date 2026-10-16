from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views.auth_view import (
    GoogleSignInView,
    PasswordResetViewSet,
    RegisterUserView,
    SignInView,
)
from .views.brand_view import BrandViewSet, SetActiveBrandView
from .views.invitation_view import (
    AcceptInvitationView,
    BrandInvitationView,
    BrandMemberDetailView,
    BrandMemberListView,
    InvitationDetailsView,
    RegisterAndAcceptInvitationView,
    ResendInvitationView,
    RevokeInvitationView,
)
from .views.user_view import CurrentUserView, OnboardingView

router = DefaultRouter()
router.register(r"password-reset", PasswordResetViewSet, basename="password-reset")
router.register(r"brands", BrandViewSet, basename="brand")

urlpatterns = [
    path("sign-in/", SignInView.as_view(), name="sign-in"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", RegisterUserView.as_view(), name="register"),
    path("google-sign-in/", GoogleSignInView.as_view(), name="google-sign-in"),
    path("onboarding/", OnboardingView.as_view(), name="onboarding"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("me/active-brand/", SetActiveBrandView.as_view(), name="set-active-brand"),
    # Brand invitations & members
    path(
        "brands/<uuid:brand_id>/invitations/",
        BrandInvitationView.as_view(),
        name="brand-invitations",
    ),
    path(
        "brands/<uuid:brand_id>/invitations/<uuid:invitation_id>/",
        RevokeInvitationView.as_view(),
        name="brand-invitation-revoke",
    ),
    path(
        "brands/<uuid:brand_id>/invitations/<uuid:invitation_id>/resend/",
        ResendInvitationView.as_view(),
        name="brand-invitation-resend",
    ),
    path(
        "brands/<uuid:brand_id>/members/",
        BrandMemberListView.as_view(),
        name="brand-members",
    ),
    path(
        "brands/<uuid:brand_id>/members/<uuid:member_id>/",
        BrandMemberDetailView.as_view(),
        name="brand-member-detail",
    ),
    # Public invitation token actions
    path(
        "invitations/<str:token>/",
        InvitationDetailsView.as_view(),
        name="invitation-details",
    ),
    path(
        "invitations/<str:token>/accept/",
        AcceptInvitationView.as_view(),
        name="invitation-accept",
    ),
    path(
        "invitations/<str:token>/register/",
        RegisterAndAcceptInvitationView.as_view(),
        name="invitation-register-accept",
    ),
    path("", include(router.urls)),
]
