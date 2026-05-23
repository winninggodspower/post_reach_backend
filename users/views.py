from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from integrations.services.google_auth_service import GoogleAuthService
from .serializers import GoogleAuthSerializer, RegisterUserSerializer

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

# Create your views here.
class RegisterUserView(generics.CreateAPIView):
    serializer_class = RegisterUserSerializer

class GoogleLoginView(APIView):
    serializer_class = GoogleAuthSerializer

    def post(self, request):
        serializer = self.serializer_class(request.data)
        serializer.is_valid(raise_exception=True)

        try:

            google_helper = GoogleAuthService(
                redirect_uri=serializer.validated_data['redirect_uri']
            )

            user_info = google_helper.verify_and_get_user_info(serializer.validated_data['auth_code'])
            email = user_info['email']
            first_name = user_info['first_name']
            last_name = user_info['last_name']

            # Get or create user
            user, created = User.objects.get_or_create(email=email, defaults={
                'first_name': first_name,
                'last_name': last_name,
            })

            # Return JWT token
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })

        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Catch any other unexpected errors
            print(f"Authentication error: {e}") # Log the full exception for debugging
            return Response({'detail': 'An unexpected error occurred during authentication.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
