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
    path("", include(router.urls)),
]
