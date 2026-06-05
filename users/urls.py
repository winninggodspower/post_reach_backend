from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CurrentUserView, GoogleSignInView, OnboardingView, RegisterUserView, SignInView

urlpatterns = [
    path('sign-in/', SignInView.as_view(), name='sign-in'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', RegisterUserView.as_view(), name='register'),
    path('google-sign-in/', GoogleSignInView.as_view(), name='google-sign-in'),
    path('onboarding/', OnboardingView.as_view(), name='onboarding'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
]
