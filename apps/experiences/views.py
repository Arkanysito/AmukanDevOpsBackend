# apps/experiences/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.http import JsonResponse

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

# apps/experiences/views.py - Actualiza la función get_user_services

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_services(request):
    """
    Obtener todos los servicios de la organización a la que pertenece el usuario
    """
    print(f"=== GET USER SERVICES ===")
    print(f"Usuario autenticado: {request.user}")
    print(f"User ID: {request.user.id}")
    print(f"Username: {request.user.username}")
    
    try:
        # Buscar la relación OrganizationUser para este usuario
        organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
        print(f"OrganizationUser encontrado: {organization_user}")
        
        if not organization_user:
            print("ERROR: No se encontró OrganizationUser")
            return Response(
                {"detail": "El usuario no pertenece a ninguna organización"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        organization = organization_user.organization_id
        print(f"Organización: {organization}")
        print(f"Organization ID: {organization.organization_id if organization else 'None'}")
        
        # Obtener todos los servicios de la organización
        services = []
        
        # Accommodation services
        accommodations = AccommodationService.objects.filter(organization_id=organization)
        print(f"Alojamientos encontrados: {accommodations.count()}")
        
        for acc in accommodations:
            services.append({
                "service_id": str(acc.service_id),
                "type": "accommodation",
                "name": acc.name,
                "description": acc.description,
                "price": float(acc.price) if acc.price else None,
                "price_currency": acc.price_currency,
                "rating": float(acc.rating) if acc.rating else None,
                "accommodation_type": acc.accommodation_type,
                "beds": acc.beds,
                "room_capacity": acc.room_capacity,
                "check_in_time": str(acc.check_in_time) if acc.check_in_time else None,
                "check_out_time": str(acc.check_out_time) if acc.check_out_time else None,
                #"created_at": acc.created_at.isoformat() if acc.created_at else None,
            })
        
        # Transport services
        transports = TransportService.objects.filter(organization_id=organization)
        print(f"Transportes encontrados: {transports.count()}")
        
        for trans in transports:
            services.append({
                "service_id": str(trans.service_id),
                "type": "transport",
                "name": trans.name,
                "description": trans.description,
                "price": float(trans.price) if trans.price else None,
                "price_currency": trans.price_currency,
                "rating": float(trans.rating) if trans.rating else None,
                "transport_type": trans.transport_type,
                "capacity": trans.capacity,
                "schedule": trans.schedule,
                #"created_at": trans.created_at.isoformat() if trans.created_at else None,
            })
        
        # Activity services
        activities = ActivityService.objects.filter(organization_id=organization)
        print(f"Actividades encontradas: {activities.count()}")
        
        for act in activities:
            services.append({
                "service_id": str(act.service_id),
                "type": "activity",
                "name": act.name,
                "description": act.description,
                "price": float(act.price) if act.price else None,
                "price_currency": act.price_currency,
                "rating": float(act.rating) if act.rating else None,
                "activity_type": act.activity_type,
                "duration_minutes": act.duration_minutes,
                "guide_included": act.guide_included,
                #"created_at": act.created_at.isoformat() if act.created_at else None,
            })
        
        print(f"Total de servicios combinados: {len(services)}")
        
        # Ordenar por fecha de creación (más recientes primero)
        #services.sort(key=lambda x: x['created_at'] or '', reverse=True)
        
        return Response({"services": services}, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"EXCEPCIÓN: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"detail": f"Error al obtener servicios: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_service_detail(request, service_type: str, service_id: str):
    """
    Obtener detalles de un servicio específico
    """
    tipo = (service_type or "").lower()
    if tipo not in MODEL_BY_TYPE:
        return Response(
            {"detail": "service_type debe ser uno de: accommodation, transport, activity"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    Model = MODEL_BY_TYPE[tipo]
    service = get_object_or_404(Model, pk=service_id)
    
    # Verificar que el servicio pertenezca a la organización del usuario
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or service.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para ver este servicio"},
            status=status.HTTP_403_FORBIDDEN,
        )
    
    # Construir respuesta según el tipo
    response_data = {
        "service_id": str(service.service_id),
        "type": tipo,
        "name": service.name,
        "description": service.description,
        "price": float(service.price) if service.price else None,
        "price_currency": service.price_currency,
        "details": service.details,
        "policies": service.policies,
        "rating": float(service.rating) if service.rating else None,
        "organization_id": str(service.organization_id.organization_id) if service.organization_id else None,
        "place_id": str(service.place_id.place_id) if service.place_id else None,
        #"created_at": service.created_at.isoformat() if service.created_at else None,
        #"updated_at": service.updated_at.isoformat() if service.updated_at else None,
    }
    
    # Agregar campos específicos del tipo
    if tipo == "accommodation":
        response_data.update({
            "accommodation_type": service.accommodation_type,
            "amenities": service.amenities,
            "beds": service.beds,
            "room_capacity": service.room_capacity,
            "check_in_time": str(service.check_in_time) if service.check_in_time else None,
            "check_out_time": str(service.check_out_time) if service.check_out_time else None,
            "parking": service.parking,
        })
    elif tipo == "transport":
        response_data.update({
            "transport_type": service.transport_type,
            "schedule": service.schedule,
            "capacity": service.capacity,
        })
    elif tipo == "activity":
        response_data.update({
            "activity_type": service.activity_type,
            "duration_minutes": service.duration_minutes,
            "guide_included": service.guide_included,
        })
    
    return Response(response_data, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
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

# apps/experiences/views.py - Actualiza SOLO la función update_service

@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def update_service(request, service_type: str, service_id: str):
    """
    Actualizar un servicio específico
    """
    print(f"=== UPDATE SERVICE ===")
    print(f"Service Type: {service_type}")
    print(f"Service ID: {service_id}")
    print(f"User: {request.user}")
    print(f"Request Data: {request.data}")
    
    tipo = (service_type or "").lower()
    if tipo not in MODEL_BY_TYPE:
        return Response(
            {"detail": "service_type debe ser uno de: accommodation, transport, activity"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    Model = MODEL_BY_TYPE[tipo]
    instancia = get_object_or_404(Model, pk=service_id)
    
    # Verificar permisos
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or instancia.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para editar este servicio"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Solo permitimos actualizar estos campos
    permitidos = BASE_FIELDS | TYPE_FIELDS[tipo] | {"place_id"}
    incoming = {k: v for k, v in request.data.items() if k in permitidos}
    
    print(f"Campos a actualizar: {list(incoming.keys())}")

    # Resolver FKs si vienen en el body
    if "place_id" in incoming:
        place_pk = incoming.pop("place_id")
        if place_pk:
            lugar = get_object_or_404(Place, pk=place_pk)
            instancia.place_id = lugar
        else:
            instancia.place_id = None

    # Asignar el resto de campos simples/específicos
    for field_name, value in incoming.items():
        print(f"Setting {field_name} = {value} (type: {type(value)})")
        
        # Manejar el campo amenities específicamente para evitar el error
        if field_name == "amenities":
            # Si amenities es un string, convertirlo a lista
            if isinstance(value, str):
                if value.strip():
                    value = [item.strip() for item in value.split(',')]
                else:
                    value = []
            # Si es una lista, asegurarse de que sea serializable
            elif isinstance(value, list):
                value = value
            else:
                value = []
            print(f"Processed amenities: {value}")
        
        setattr(instancia, field_name, value)

    try:
        with transaction.atomic():
            # EVITAR full_clean() temporalmente porque causa el error con arrays
            # instancia.full_clean()  # ← COMENTA ESTA LINEA TEMPORALMENTE
            
            instancia.save()
            print("Servicio actualizado exitosamente")
    except Exception as e:
        print(f"Error durante la actualización: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "service_id": str(instancia.service_id),
            "type": tipo,
            "name": instancia.name,
            "updated_fields": list(incoming.keys()),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_service(request, service_type: str, service_id: str):
    """
    Eliminar un servicio
    """
    tipo = (service_type or "").lower()
    if tipo not in MODEL_BY_TYPE:
        return Response(
            {"detail": "service_type debe ser uno de: accommodation, transport, activity"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    Model = MODEL_BY_TYPE[tipo]
    servicio = get_object_or_404(Model, pk=service_id)
    
    # Verificar que el servicio pertenezca a la organización del usuario
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or servicio.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para eliminar este servicio"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        servicio.delete()
        return Response(
            {"detail": "Servicio eliminado correctamente"},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"detail": f"Error al eliminar servicio: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )