from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import UserFavorite
from .serializers import UserFavoriteSerializer, resolve_content_type_for_target_type


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_user_favorites(request):
    """
    Lista los favoritos del usuario autenticado.
    ?target_type=accommodation|transport|activity|place|event (opcional)
    """
    queryset = UserFavorite.objects.filter(user=request.user).select_related("content_type")

    selected_target_type = request.query_params.get("target_type")
    if selected_target_type:
        ct = resolve_content_type_for_target_type(selected_target_type)
        queryset = queryset.filter(content_type=ct)

    data = UserFavoriteSerializer(queryset, many=True, context={"request": request}).data
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_user_favorite(request):
    """
    Crea (idempotente) un favorito.
    Body: {"target_type": "...", "target_id": "<uuid>"}
    """
    serializer = UserFavoriteSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    favorite = serializer.save()
    return Response(UserFavoriteSerializer(favorite).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_user_favorite(request):
    """
    Elimina un favorito por (target_type, target_id).
    Se aceptan por body o por query params.
    """
    target_type = request.data.get("target_type") or request.query_params.get("target_type")
    target_id = request.data.get("target_id") or request.query_params.get("target_id")

    if not target_type or not target_id:
        return Response({"detail": "Se requieren 'target_type' y 'target_id'."}, status=400)

    try:
        ct = resolve_content_type_for_target_type(target_type)
    except Exception as e:
        return Response({"detail": str(e)}, status=400)

    deleted, _ = UserFavorite.objects.filter(
        user=request.user, content_type=ct, object_id=target_id
    ).delete()

    if deleted:
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response({"detail": "Favorito no encontrado."}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_user_favorite(request):
    """
    Toggle: si existe lo elimina; si no existe lo crea.
    Body: {"target_type": "...", "target_id": "<uuid>"}
    """
    serializer = UserFavoriteSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    ct = serializer.validated_data["content_type"]
    oid = serializer.validated_data["object_id"]

    existing = UserFavorite.objects.filter(user=request.user, content_type=ct, object_id=oid).first()
    if existing:
        existing.delete()
        return Response({"toggled": "removed"}, status=200)

    created = UserFavorite.objects.create(user=request.user, content_type=ct, object_id=oid)
    return Response({"toggled": "added", "favorite": UserFavoriteSerializer(created).data}, status=201)