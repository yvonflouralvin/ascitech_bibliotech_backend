from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """POST /api/apps/users/logout/  body: {"refresh": "..."}

    Revoque le refresh token en le placant sur la liste noire, de sorte qu'il ne
    puisse plus servir a obtenir de nouveaux access tokens.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response(
                {"detail": "Le champ 'refresh' est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            # Token deja expire, deja revoque ou invalide : la session est de
            # toute facon terminee cote client, on ne fait pas echouer l'appel.
            return Response(status=status.HTTP_205_RESET_CONTENT)

        return Response(status=status.HTTP_205_RESET_CONTENT)
