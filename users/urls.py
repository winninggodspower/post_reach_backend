from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import GoogleLoginView, RegisterUserView, SignInView

urlpatterns = [
    path('login/', SignInView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', RegisterUserView.as_view(), name='register'),
    path('google-login/', GoogleLoginView.as_view(), name='google-login'),
]
