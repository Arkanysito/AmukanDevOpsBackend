from django.shortcuts import render
from .models import CustomUser
from rest_framework import generics
from .serializers import UserSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse

class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "username": request.user.username,
            "email": request.user.email,
        })
    
class UsernameAvailabilityView(APIView):
    def get(self, request):
        username = request.query_params.get("username")
        if not username:
            return Response({"error": "Username requerido"}, status=status.HTTP_400_BAD_REQUEST)

        exists = CustomUser.objects.filter(username__iexact=username).exists()
        return Response({"available": not exists})
    
class EmailAvailabilityView(APIView):
    def get(self, request):
        email = request.query_params.get("email", "").strip().lower()
        if not email:
            return Response({"available": False, "error": "Email no proporcionado"}, status=status.HTTP_400_BAD_REQUEST)

        exists = CustomUser.objects.filter(email=email).exists()
        return Response({"available": not exists})



