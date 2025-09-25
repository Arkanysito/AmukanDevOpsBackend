# apps/experiences/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from apps.organizations.models import Organization, OrganizationUser
from apps.location.models import Place
from apps.experiences.models import (
    AccommodationService,
    TransportService,
    ActivityService,
)

# Campos base comunes a todos los servicios
BASE_FIELDS = {
    "name", "description", "price", "price_currency", "details", "policies", "rating"
}

# Campos específicos por tipo
TYPE_FIELDS = {
    "accommodation": {
        "accommodation_type",
        "amenities",
        "beds",
        "room_capacity",
        "check_in_time",
        "check_out_time",
        "parking",
    },
    "transport": {"transport_type", "schedule", "capacity"},
    "activity": {"activity_type", "duration_minutes", "guide_included"},
}


REQUIRED_BY_TYPE = {
    "accommodation": {"accommodation_type", "beds", "room_capacity", "check_in_time", "check_out_time"},
    "transport": {"transport_type"},
    "activity": {"activity_type", "duration_minutes"},
}

MODEL_BY_TYPE = {
    "accommodation": AccommodationService,
    "transport": TransportService,
    "activity": ActivityService,
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])  # Ahora requiere autenticación
def create_service(request):
    service_type = (request.data.get("service_type") or "").lower()
    if service_type not in MODEL_BY_TYPE:
        return Response(
            {"detail": "service_type debe ser uno de: accommodation, transport, activity"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Obtener la organización del usuario autenticado
    try:
        # Buscar la relación OrganizationUser para este usuario
        organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
        
        if not organization_user:
            return Response(
                {"detail": "El usuario no pertenece a ninguna organización"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        organization = organization_user.organization_id
        
    except OrganizationUser.DoesNotExist:
        return Response(
            {"detail": "El usuario no pertenece a ninguna organización"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    place = None
    place_id = request.data.get("place_id")
    if place_id:
        place = get_object_or_404(Place, pk=place_id)

    # Aceptar solo campos permitidos para el tipo
    allowed = BASE_FIELDS | TYPE_FIELDS[service_type]
    payload = {k: v for k, v in request.data.items() if k in allowed}

    # Validación de requeridos
    missing = []
    for f in ("name", "price", "price_currency"):
        if payload.get(f) in (None, ""):
            missing.append(f)
    for f in REQUIRED_BY_TYPE[service_type]:
        if payload.get(f) in (None, ""):
            missing.append(f)
    if missing:
        return Response(
            {"detail": "Faltan campos requeridos", "fields": sorted(set(missing))},
            status=status.HTTP_400_BAD_REQUEST,
        )

    
    payload["organization_id"] = organization
    payload["place_id"] = place

    Model = MODEL_BY_TYPE[service_type]
    try:
        with transaction.atomic():
            obj = Model.objects.create(**payload)
    except (IntegrityError, ValidationError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": f"Error al crear servicio: {e}"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "service_id": str(getattr(obj, "service_id", obj.pk)),
            "type": service_type,
            "name": obj.name,
        },
        status=status.HTTP_201_CREATED,
    )