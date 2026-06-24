from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CurrentUserView,
    GoogleSignInView,
    OnboardingView,
    PasswordResetViewSet,
    RegisterUserView,
    SignInView,
)

router = DefaultRouter()
router.register(r"password-reset", PasswordResetViewSet, basename="password-reset")

urlpatterns = [
    path("sign-in/", SignInView.as_view(), name="sign-in"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", RegisterUserView.as_view(), name="register"),
    path("google-sign-in/", GoogleSignInView.as_view(), name="google-sign-in"),
    path("onboarding/", OnboardingView.as_view(), name="onboarding"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("", include(router.urls)),
]
