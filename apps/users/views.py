from uuid import UUID

from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CustomUser
from .serializers import UserSerializer

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

def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(str(value)); return True
    except Exception:
        return False

def _get_user_by_identifier(user_id: str, request):
    """
    'me' => request.user
    UUID => lookup por id
    otro => lookup por username
    """
    if user_id == "me":
        return request.user
    lookup = {"id": user_id} if _looks_like_uuid(user_id) else {"username": user_id}
    return get_object_or_404(CustomUser, **lookup)

def _require_self_permission(request, target_user: CustomUser, action: str):
    """
    Self-only. Devuelve 403 si no es el dueño.
    """
    if target_user.id != request.user.id:
        return Response(
            {"detail": f"Solo puedes {action} tu propio usuario."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_detail(request, user_id: str):
    """
    Detalle de usuario (self-only).
    Acepta: 'me' | <uuid> | <username>
    """
    obj = _get_user_by_identifier(user_id, request)
    err = _require_self_permission(request, obj, "ver")
    if err:
        return err

    data = {
        "id": str(obj.id),
        "username": obj.username,
        "email": obj.email,
        "first_name": obj.first_name,
        "last_name": obj.last_name,
        "gender": obj.gender,
        "nationality": obj.nationality,
        "language": obj.language,
        "currency": obj.currency,
    }
    return Response(data, status=status.HTTP_200_OK)

@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def update_user(request, user_id: str):
    """
    Actualizar usuario (self-only).
    """
    obj = _get_user_by_identifier(user_id, request)
    err = _require_self_permission(request, obj, "editar")
    if err:
        return err

    partial = (request.method == "PATCH")
    ser = UserSerializer(obj, data=request.data, partial=partial)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            user = ser.save()
    except IntegrityError as e:
        msg = str(e).lower()
        if "email" in msg and "unique" in msg:
            return Response({"detail": "Email ya está en uso"}, status=status.HTTP_400_BAD_REQUEST)
        if "username" in msg and "unique" in msg:
            return Response({"detail": "Username ya está en uso"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Violación de unicidad o integridad"}, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    data = {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "gender": user.gender,
        "nationality": user.nationality,
        "language": user.language,
        "currency": user.currency,
    }
    return Response(data, status=status.HTTP_200_OK)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id: str):
    """
    Eliminar usuario (self-only).
    Acepta 'me' | <uuid> | <username>
    """
    obj = _get_user_by_identifier(user_id, request)
    err = _require_self_permission(request, obj, "eliminar")
    if err:
        return err

    try:
        obj.delete()
        return Response({"detail": "Usuario eliminado correctamente"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": f"Error al eliminar usuario: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

