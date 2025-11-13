# apps/users/views.py

from uuid import UUID
from django.db.models import Prefetch, prefetch_related_objects
from collections import defaultdict
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError, models
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
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

from apps.recommendation.services import invalidate_user_vector_cache

# Importar modelos necesarios para la búsqueda ambigua
from apps.experiences.models import ActivityService, Event
from apps.location.models import Place

from apps.tracking.models import Interaction
from apps.core.constants import InteractionAction
from .tasks import run_profile_analysis_task, clear_user_vector_cache_task
import logging
from apps.core.s3_utils import build_public_url

logger = logging.getLogger(__name__) # Configurar logger

class CreateUserView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = CustomUser.objects.prefetch_related(
                'organizationuser_set__organization_id'
            ).get(id=request.user.id)
        except CustomUser.DoesNotExist:
             return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserSerializer(user)
        return Response(serializer.data)

    
    def patch(self, request):
        user = request.user
        serializer = UserSerializer(user, data=request.data, partial=True)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                updated_user = serializer.save()
        except IntegrityError as e:
            msg = str(e).lower()
            if "email" in msg and "unique" in msg:
                return Response({"detail": "Email ya está en uso"}, status=status.HTTP_400_BAD_REQUEST)
            if "username" in msg and "unique" in msg:
                return Response({"detail": "Username ya está en uso"}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": "Violación de unicidad o integridad"}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Devolver el objeto serializado completo para mantener consistencia
        # El serializer buscará la data de org (fallback)
        return Response(UserSerializer(updated_user).data, status=status.HTTP_200_OK)

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
        if not request.user.is_authenticated:
             raise Http404("Usuario no autenticado") # O PermissionDenied
        return request.user
    lookup = {"id": user_id} if _looks_like_uuid(user_id) else {"username": user_id}
    return get_object_or_404(CustomUser, **lookup)


def _require_self_permission(request, target_user: CustomUser, action: str):
    """
    Self-only. Devuelve 403 si no es el dueño.
    """
    if not request.user.is_authenticated or target_user.id != request.user.id: # Check auth status
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
    try:
        obj = _get_user_by_identifier(user_id, request)
    except Http404 as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
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
    try:
        obj = _get_user_by_identifier(user_id, request)
    except Http404 as e:
        return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
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
        logger.error(f"IntegrityError al actualizar usuario {user_id}: {e}")
        return Response({"detail": "Violación de unicidad o integridad"}, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        logger.error(f"ValidationError al actualizar usuario {user_id}: {e}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error inesperado al actualizar usuario {user_id}: {e}", exc_info=True)
        return Response({"detail": "Error interno al actualizar usuario"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
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
    try:
        obj = _get_user_by_identifier(user_id, request)
    except Http404 as e:
         return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

    err = _require_self_permission(request, obj, "eliminar")
    if err:
        return err

    try:
        obj.delete()
        return Response({"detail": "Usuario eliminado correctamente"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error al eliminar usuario {user_id}: {e}", exc_info=True)
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
        if not isinstance(interest_ids, list):
            return Response({"detail": "El campo 'interests' debe ser una lista de IDs."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            valid_interest_ids = []
            for interest_id in interest_ids:
                try:
                    valid_interest_ids.append(UUID(str(interest_id)))
                except ValueError:
                    logger.warning(f"ID de interés inválido '{interest_id}' recibido para usuario {user.id}")
                    continue
            with transaction.atomic():
                UserInterest.objects.filter(user_id=user).delete()
                existing_interests = Interest.objects.filter(interest_id__in=valid_interest_ids).values_list('interest_id', flat=True)
                interests_to_create = []
                for interest_uuid in existing_interests:
                    interests_to_create.append(
                        UserInterest(
                            user_id=user,
                            interest_id_id=interest_uuid,
                            weight=1.0
                        )
                    )
                if interests_to_create:
                    UserInterest.objects.bulk_create(interests_to_create)
            try:
                invalidate_user_vector_cache(user.id)
                logger.info(f"Intereses guardados para {user.id}. Cache de vector invalidado sincrónicamente.")
            except Exception as cache_err:
                logger.error(f"Error al invalidar cache sincrónicamente para user {user.id}: {cache_err}")
            return Response({"detail": "Intereses guardados correctamente"}, status=status.HTTP_200_OK)

        except Interest.DoesNotExist:
            return Response({"detail": "Uno o más intereses no existen"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error al guardar intereses para usuario {user.id}: {e}", exc_info=True)
            return Response({"detail": f"Error al guardar intereses: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        user = request.user
        user_interests = UserInterest.objects.filter(user_id=user).select_related('interest_id')
        interest_data = [{
            "id": str(interest.interest_id.interest_id),
            "name": interest.interest_id.name
        } for interest in user_interests]
        return Response(interest_data)

def find_content_type_for_activity_or_place(target_id_uuid: UUID):
    """
    Intenta encontrar un ActivityService o un Place con el UUID dado.
    Devuelve (ContentType, object_id) si lo encuentra, o (None, None) si no.
    """
    try:
        activity_ct = ContentType.objects.get_for_model(ActivityService)
        if ActivityService.objects.filter(service_id=target_id_uuid).exists():
            return activity_ct, target_id_uuid
    except ContentType.DoesNotExist:
         logger.error("ContentType para ActivityService no encontrado.")
         # Continuar para buscar Place

    try:
        place_ct = ContentType.objects.get_for_model(Place)
        if Place.objects.filter(place_id=target_id_uuid).exists():
            return place_ct, target_id_uuid
    except ContentType.DoesNotExist:
        logger.error("ContentType para Place no encontrado.")

    return None, None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_user_favorites(request):
    try:
        # 1. Consulta base (SIN el prefetch que fallaba)
        favorites_qs = UserFavorite.objects.filter(user_id=request.user).select_related("content_type")

        target_type_str = request.query_params.get("target_type")
        if target_type_str:
            try:
                if target_type_str.lower() == 'activity':
                    activity_ct_id = ContentType.objects.get_for_model(ActivityService).id
                    place_ct_id = ContentType.objects.get_for_model(Place).id
                    favorites_qs = favorites_qs.filter(content_type_id__in=[activity_ct_id, place_ct_id])
                else:
                    content_type = resolve_content_type_for_target_type(target_type_str)
                    favorites_qs = favorites_qs.filter(content_type=content_type)
            except Exception as exc:
                logger.error(f"Error resolviendo ContentType para '{target_type_str}': {exc}")
                return Response({"detail": f"Tipo de objetivo inválido: {target_type_str}"}, status=status.HTTP_400_BAD_REQUEST)
        
        # 3. Paso 1: Prefetch simple del GenericForeignKey 'target'
        favorites_qs = favorites_qs.prefetch_related('target')
        
        # 4. Ejecutar la consulta (convertir a lista)
        favorites_list = list(favorites_qs)

        # 5. Agrupar los 'targets' por su tipo (Modelo)
        targets_by_type = defaultdict(list)
        for favorite in favorites_list:
            if favorite.target: # 'target' fue prefetched
                targets_by_type[favorite.target.__class__].append(favorite.target)

        # 6. Paso 2: Prefetch ANIDADO manual para 'cover_image'
        # Esto es muy eficiente: hará una consulta por CADA TIPO de modelo, 
        # (ej. 1 para Place, 1 para Event), no por cada item.
        for model_class, targets in targets_by_type.items():
            if hasattr(model_class, 'cover_image'):
                prefetch_related_objects(targets, 'cover_image')

        payload = []
        
        # 7. Este bucle ahora es 100% rápido
        for favorite in favorites_list: # Usamos la lista ya cargada
            target_display = "Objeto no disponible"
            target_details = {}
            target_obj = favorite.target # Acceder al objeto prefetched

            if target_obj:
                target_display = getattr(target_obj, "name", None) or getattr(target_obj, "title", None) or str(target_obj)
                model_type_name = favorite.content_type.model
                target_details['model_type'] = model_type_name

                if hasattr(target_obj, "cover_image") and target_obj.cover_image:
                    try:
                        target_details["cover_image_url"] = build_public_url(
                            target_obj.cover_image.bucket,
                            target_obj.cover_image.object_key
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo construir cover_image_url para favorito {favorite.user_fav_id}: {e}")

                # Otros detalles específicos
                if isinstance(target_obj, Place):
                    target_details['place_type'] = getattr(target_obj, 'type', None)
                elif isinstance(target_obj, ActivityService):
                    target_details['activity_duration'] = getattr(target_obj, 'duration_minutes', None)
                elif isinstance(target_obj, Event):
                    target_details['event_start_date'] = getattr(target_obj, 'start_date', None)

            payload.append({
                "user_fav_id": str(favorite.user_fav_id),
                "target_type": f"{favorite.content_type.app_label}.{favorite.content_type.model}",
                "target_id": str(favorite.object_id),
                "target_display_label": target_display,
                "target_details": target_details,
            })

        return Response(payload)

    except ValueError as ve: # Captura el error específico que tuviste
        logger.error(f"Error de ValueError en list_user_favorites (probable N+1): {str(ve)}", exc_info=True)
        return Response(
            {"detail": f"Error de configuración del servidor al pre-cargar datos: {ve}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        logger.error(f"Error en list_user_favorites: {str(e)}", exc_info=True)
        return Response(
            {"detail": "Error interno del servidor al obtener favoritos"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_user_favorite(request):
    target_type_str = request.data.get("target_type")
    target_id_str = request.data.get("target_id")
    user = request.user

    if not target_type_str or not target_id_str:
        return Response({"detail": "Se requieren 'target_type' y 'target_id'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        target_id_uuid = UUID(str(target_id_str))
    except ValueError:
        return Response({"detail": "El 'target_id' debe ser un UUID válido."}, status=status.HTTP_400_BAD_REQUEST)

    content_type = None
    object_id = None

    if target_type_str.lower() == 'activity':
        content_type, object_id = find_content_type_for_activity_or_place(target_id_uuid)
        if content_type is None:
             logger.warning(f"Intento de añadir favorito 'activity' fallido: No se encontró ActivityService ni Place con ID {target_id_uuid}")
             return Response({"detail": f"No se encontró una actividad o lugar con el ID {target_id_uuid}."}, status=status.HTTP_404_NOT_FOUND)
    else:
        # Para otros tipos, usar la lógica original
        try:
            content_type = resolve_content_type_for_target_type(target_type_str)
            # Verificar si el objeto existe (opcional pero recomendado)
            ModelClass = content_type.model_class()
            if not ModelClass.objects.filter(pk=target_id_uuid).exists(): # Usar pk genérico
                 logger.warning(f"Intento de añadir favorito '{target_type_str}' fallido: Objeto con ID {target_id_uuid} no existe.")
                 return Response({"detail": f"No se encontró un objeto de tipo '{target_type_str}' con el ID {target_id_uuid}."}, status=status.HTTP_404_NOT_FOUND)
            object_id = target_id_uuid
        except Exception as exc:
             logger.error(f"Error resolviendo ContentType o buscando objeto para '{target_type_str}' / {target_id_uuid}: {exc}")
             return Response({"detail": f"Tipo de objetivo inválido o error: {str(exc)}"}, status=status.HTTP_400_BAD_REQUEST)

    if content_type and object_id:
        try:
            favorite, created = UserFavorite.objects.get_or_create(
                user_id=user,
                content_type=content_type,
                object_id=object_id
            )
            if created:
                # Registrar interacción
                # Interaction.objects.create(...)
                serializer = UserFavoriteSerializer(favorite) # Serializar para la respuesta
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                serializer = UserFavoriteSerializer(favorite)
                return Response(serializer.data, status=status.HTTP_200_OK) # Ya existía

        except IntegrityError: # Por si acaso, aunque get_or_create lo maneja
             logger.warning(f"IntegrityError al añadir favorito para {user.id}, CT {content_type.id}, ID {object_id}")
             return Response({"detail": "Este favorito ya existe (error de integridad)."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
             logger.error(f"Error inesperado al añadir favorito: {e}", exc_info=True)
             return Response({"detail": "Error interno al añadir favorito."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
         # Esto no debería pasar si la lógica anterior es correcta, pero por seguridad
         return Response({"detail": "No se pudo determinar el tipo de contenido o ID."}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_user_favorite(request):
    target_type_str = request.data.get("target_type") or request.query_params.get("target_type")
    target_id_str = request.data.get("target_id") or request.query_params.get("target_id")
    user = request.user

    if not target_type_str or not target_id_str:
        return Response({"detail": "Se requieren 'target_type' y 'target_id'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        target_id_uuid = UUID(str(target_id_str))
    except ValueError:
        return Response({"detail": "El 'target_id' debe ser un UUID válido."}, status=status.HTTP_400_BAD_REQUEST)

    content_type = None

    if target_type_str.lower() == 'activity':
        # Para eliminar, necesitamos saber el tipo exacto que está guardado
        # Buscamos el favorito existente que coincida con el ID y el usuario
        favorite_to_delete = UserFavorite.objects.filter(
            user_id=user,
            object_id=target_id_uuid,
            # Podría ser ActivityService O Place
            content_type__in=[
                ContentType.objects.get_for_model(ActivityService),
                ContentType.objects.get_for_model(Place)
            ]
        ).first()

        if not favorite_to_delete:
            logger.warning(f"Intento de eliminar favorito 'activity' fallido: No se encontró favorito para ID {target_id_uuid} y usuario {user.id}")
            return Response({"detail": "Favorito no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Usar el content_type encontrado
        content_type = favorite_to_delete.content_type

    else:
        # Para otros tipos, usar la lógica original
        try:
            content_type = resolve_content_type_for_target_type(target_type_str)
        except Exception as exc:
            logger.error(f"Error resolviendo ContentType para '{target_type_str}': {exc}")
            return Response({"detail": f"Tipo de objetivo inválido: {target_type_str}"}, status=status.HTTP_400_BAD_REQUEST)

    if content_type:
        try:
            deleted_rows, _ = UserFavorite.objects.filter(
                user_id=user, content_type=content_type, object_id=target_id_uuid
            ).delete()

            if deleted_rows:
                 # Registrar interacción
                 # Interaction.objects.create(...)
                return Response(status=status.HTTP_204_NO_CONTENT)
            else:
                 # Si llegamos aquí con un tipo específico (no 'activity'), significa que no existía
                 logger.warning(f"Intento de eliminar favorito '{target_type_str}' fallido: No se encontró favorito para ID {target_id_uuid} y usuario {user.id} con CT {content_type.id}")
                 return Response({"detail": "Favorito no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error inesperado al eliminar favorito: {e}", exc_info=True)
            return Response({"detail": "Error interno al eliminar favorito."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
         # Caso 'activity' donde no se encontró el favorito en la búsqueda inicial
         return Response({"detail": "Favorito no encontrado (lógica interna)."}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_user_favorite(request):
    # Ya no usamos el serializer directamente para determinar el CT
    # serializer = UserFavoriteSerializer(data=request.data, context={"request": request})
    # if not serializer.is_valid():
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    # content_type = serializer.validated_data["content_type"]
    # object_uuid = serializer.validated_data["object_id"]

    target_type_str = request.data.get("target_type")
    target_id_str = request.data.get("target_id")
    user = request.user

    if not target_type_str or not target_id_str:
        return Response({"detail": "Se requieren 'target_type' y 'target_id'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        target_id_uuid = UUID(str(target_id_str))
    except ValueError:
        return Response({"detail": "El 'target_id' debe ser un UUID válido."}, status=status.HTTP_400_BAD_REQUEST)

    content_type = None
    object_id = None
    found_object = False # Flag para saber si el objeto referenciado existe

    if target_type_str.lower() == 'activity':
        # Intentar buscar el tipo correcto
        content_type, object_id = find_content_type_for_activity_or_place(target_id_uuid)
        if content_type is not None:
             found_object = True # Sabemos que el objeto existe porque la función lo verificó
        else:
             logger.warning(f"Toggle favorito 'activity': No se encontró ActivityService ni Place con ID {target_id_uuid}")
             # A diferencia de remove/add, en toggle podríamos querer permitir quitar un favorito aunque el objeto ya no exista.
             # Pero para *añadirlo*, necesitamos saber qué es. Por consistencia, devolvemos error si no se encuentra.
             return Response({"detail": f"No se encontró una actividad o lugar con el ID {target_id_uuid}."}, status=status.HTTP_404_NOT_FOUND)

    else:
        # Para otros tipos, usar la lógica original para encontrar CT
        try:
            content_type = resolve_content_type_for_target_type(target_type_str)
            object_id = target_id_uuid
            # Verificar si el objeto existe
            ModelClass = content_type.model_class()
            if ModelClass.objects.filter(pk=object_id).exists(): # Usar pk genérico
                found_object = True
            #else:
                #logger.warning(f"Toggle favorito '{target_type_str}': Objeto con ID {object_id} no existe.")

        except Exception as exc:
             logger.error(f"Error resolviendo ContentType para '{target_type_str}': {exc}")
             return Response({"detail": f"Tipo de objetivo inválido: {target_type_str}"}, status=status.HTTP_400_BAD_REQUEST)

    if not content_type or not object_id:
         # Si algo falló en la lógica anterior
         return Response({"detail": "No se pudo determinar el tipo de contenido o ID."}, status=status.HTTP_400_BAD_REQUEST)


    # Intentar encontrar y borrar, o crear si no existe
    try:
        with transaction.atomic():
            existing = UserFavorite.objects.filter(
                user_id=user, content_type=content_type, object_id=object_id
            ).first()

            if existing:
                existing.delete()
                # Registrar interacción REMOVE_FAVORITE
                # Interaction.objects.create(...)
                logger.info(f"Favorito eliminado para {user.id}: CT {content_type.id}, ID {object_id}")
                return Response({"toggled": "removed"}, status=status.HTTP_200_OK)
            else:
                 # Solo crear si el objeto referenciado realmente existe
                if found_object:
                    created = UserFavorite.objects.create(
                        user_id=user, content_type=content_type, object_id=object_id
                    )
                    # Registrar interacción ADD_FAVORITE
                    # Interaction.objects.create(...)
                    logger.info(f"Favorito añadido para {user.id}: CT {content_type.id}, ID {object_id}")
                    # Serializar el objeto creado para devolverlo
                    serializer = UserFavoriteSerializer(created)
                    return Response({"toggled": "added", "favorite": serializer.data}, status=status.HTTP_201_CREATED)
                else:
                     # Si intentamos añadir un favorito a un objeto que no existe (caso 'activity' que no se encontró, u otro tipo que no existe)
                     logger.warning(f"Intento de añadir favorito a objeto inexistente: User {user.id}, CT {content_type.id}, ID {object_id}")
                     return Response({"detail": "No se puede añadir a favoritos un objeto que no existe."}, status=status.HTTP_404_NOT_FOUND)

    except IntegrityError: # Poco probable con esta lógica, pero por si acaso
         logger.error(f"IntegrityError inesperado en toggle_user_favorite: User {user.id}, CT {content_type.id}, ID {object_id}")
         return Response({"detail": "Error de integridad al modificar favorito."}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         logger.error(f"Error inesperado en toggle_user_favorite: {e}", exc_info=True)
         return Response({"detail": "Error interno al modificar favorito."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)