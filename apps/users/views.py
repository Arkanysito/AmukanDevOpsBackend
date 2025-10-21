from uuid import UUID
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import CustomUser, Interest, UserInterest, UserFavorite
from .serializers import (
    UserSerializer,
    UserFavoriteSerializer,
    resolve_content_type_for_target_type,
)

from apps.tracking.models import Interaction
from apps.core.constants import InteractionAction 
from .tasks import run_profile_analysis_task, clear_user_vector_cache_task

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
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "gender": request.user.gender,
            "nationality": request.user.nationality,
            "language": request.user.language,
            "currency": request.user.currency,
        })
    
    def patch(self, request):
        user = request.user
        serializer = UserSerializer(user, data=request.data, partial=True)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                updated_user = serializer.save()
                print(f"✅ User updated: {updated_user.first_name} {updated_user.last_name}")  # Debug
        except IntegrityError as e:
            msg = str(e).lower()
            if "email" in msg and "unique" in msg:
                return Response({"detail": "Email ya está en uso"}, status=status.HTTP_400_BAD_REQUEST)
            if "username" in msg and "unique" in msg:
                return Response({"detail": "Username ya está en uso"}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": "Violación de unicidad o integridad"}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "id": str(updated_user.id),
            "username": updated_user.username,
            "email": updated_user.email,
            "first_name": updated_user.first_name,
            "last_name": updated_user.last_name,
            "gender": updated_user.gender,
            "nationality": updated_user.nationality,
            "language": updated_user.language,
            "currency": updated_user.currency,
        }, status=status.HTTP_200_OK)
    
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
    
class InterestListView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        interests = Interest.objects.filter(is_active=True) if hasattr(Interest, 'is_active') else Interest.objects.all()
        interest_data = [{"id": str(interest.interest_id), "name": interest.name} for interest in interests]
        return Response(interest_data)

class UserInterestsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        interest_ids = request.data.get('interests', [])
        
        try:
            with transaction.atomic():
                UserInterest.objects.filter(user_id=user).delete()
                
                new_interests = []
                for interest_id in interest_ids:
                    interest = Interest.objects.get(interest_id=interest_id)
                    new_interests.append(
                        UserInterest(
                            user_id=user,
                            interest_id=interest,
                            weight=1.0 # Peso por defecto
                        )
                    )
                UserInterest.objects.bulk_create(new_interests)
            
            # El usuario actualizó explícitamente sus intereses.
            # No necesitamos "analizar", solo "actualizar" el caché.
            clear_user_vector_cache_task.delay(user.id)
            # ---------------------------------
                
            return Response({"detail": "Intereses guardados correctamente"}, status=status.HTTP_200_OK)
            
        except Interest.DoesNotExist:
            return Response({"detail": "Uno o más intereses no existen"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Error al guardar intereses: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
    
    def get(self, request):
        user = request.user
        user_interests = UserInterest.objects.filter(user_id=user)
        interest_data = [{
            "id": str(interest.interest_id.interest_id),
            "name": interest.interest_id.name
        } for interest in user_interests]
        return Response(interest_data)@api_view(["GET"])

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_user_favorites(request):
    try:
        favorites_qs = UserFavorite.objects.filter(user_id=request.user).select_related("content_type")

        target_type = request.query_params.get("target_type")
        if target_type:
            try:
                content_type = resolve_content_type_for_target_type(target_type)
                favorites_qs = favorites_qs.filter(content_type=content_type)
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = []
        for favorite in favorites_qs:
            target_display = None
            target_details = {}
            
            try:
                target_obj = favorite.target
                if target_obj:
                    # Obtener el nombre/título
                    target_display = getattr(target_obj, "name", None) or getattr(target_obj, "title", None) or str(target_obj)
                    
                    # Obtener detalles específicos según el tipo
                    if hasattr(target_obj, 'accommodation_type'):
                        target_details['accommodation_type'] = getattr(target_obj, 'accommodation_type', None)
                    if hasattr(target_obj, 'type'):
                        target_details['place_type'] = getattr(target_obj, 'type', None)
                    if hasattr(target_obj, 'activity_type'):
                        target_details['activity_type'] = getattr(target_obj, 'activity_type', None)
                        
            except Exception as e:
                print(f"Error obteniendo target object: {e}")
                target_display = "Objeto eliminado"

            payload.append({
                "user_fav_id": str(favorite.user_fav_id),
                "target_type": f"{favorite.content_type.app_label}.{favorite.content_type.model}",
                "target_id": str(favorite.object_id),
                "target_display_label": target_display,
                "target_details": target_details,
            })
        
        return Response(payload)
        
    except Exception as e:
        print(f"Error en list_user_favorites: {str(e)}")
        return Response(
            {"detail": "Error interno del servidor al obtener favoritos"}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_user_favorite(request):
    serializer = UserFavoriteSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    favorite = serializer.save()
    return Response(UserFavoriteSerializer(favorite).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_user_favorite(request):
    target_type = request.data.get("target_type") or request.query_params.get("target_type")
    target_id = request.data.get("target_id") or request.query_params.get("target_id")

    if not target_type or not target_id:
        return Response({"detail": "Se requieren 'target_type' y 'target_id'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        content_type = resolve_content_type_for_target_type(target_type)
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    deleted_rows, _ = UserFavorite.objects.filter(
        user_id=request.user, content_type=content_type, object_id=target_id
    ).delete()

    if deleted_rows:
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response({"detail": "Favorito no encontrado."}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_user_favorite(request):
    serializer = UserFavoriteSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    content_type = serializer.validated_data["content_type"]
    object_uuid = serializer.validated_data["object_id"]

    existing = UserFavorite.objects.filter(
        user_id=request.user, content_type=content_type, object_id=object_uuid
    ).first()
    if existing:
        existing.delete()
        return Response({"toggled": "removed"}, status=status.HTTP_200_OK)

    created = UserFavorite.objects.create(
        user_id=request.user, content_type=content_type, object_id=object_uuid
    )
    return Response({"toggled": "added", "favorite": UserFavoriteSerializer(created).data}, status=status.HTTP_201_CREATED)