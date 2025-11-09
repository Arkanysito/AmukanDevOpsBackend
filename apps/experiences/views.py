# apps/experiences/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.http import JsonResponse
import json
import logging 

from apps.organizations.models import Organization, OrganizationUser
from apps.location.models import Place
from apps.experiences.models import (
    AccommodationService,
    ActivityService,
    Event,
)
from apps.core.models import Image
from apps.core.s3_utils import build_public_url, s3_client 

logger = logging.getLogger(__name__) 

# Campos base comunes a todos los servicios
BASE_FIELDS = {
    "name", "description", "price", "price_currency", "details", "policies", "rating"
}
TYPE_FIELDS = {
    "accommodation": {
        "accommodation_type",
        "amenities",
        "beds",
        "capacity",
        "check_in_time",
        "check_out_time",
        "parking",
    },
    "transport": {"transport_type", "schedule", "capacity"},
    "activity": {"activity_type", "duration_minutes", "guide_included"},
}

REQUIRED_BY_TYPE = {
    "accommodation": {"accommodation_type", "beds", "capacity", "check_in_time", "check_out_time"},
    "transport": {"transport_type"},
    "activity": {"activity_type", "duration_minutes"},
}

MODEL_BY_TYPE = {
    "accommodation": AccommodationService,
    "activity": ActivityService,
}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_services(request):
    """
    Obtener todos los servicios de la organización a la que pertenece el usuario
    """
    try:
        organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
        if not organization_user:
            return Response(
                {"detail": "El usuario no pertenece a ninguna organización"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        organization = organization_user.organization_id
        services = []
        accommodations = AccommodationService.objects.filter(organization_id=organization).select_related('cover_image')
        
        for acc in accommodations:
            services.append({
                "service_id": str(acc.service_id), "type": "accommodation", "name": acc.name,
                "description": acc.description, "price": float(acc.price) if acc.price else None,
                "price_currency": acc.price_currency, "rating": float(acc.rating) if acc.rating else None,
                "accommodation_type": acc.accommodation_type, "beds": acc.beds,
                "capacity": acc.capacity,
                "check_in_time": str(acc.check_in_time) if acc.check_in_time else None,
                "check_out_time": str(acc.check_out_time) if acc.check_out_time else None,
                "details": acc.details,
                "cover_image_url": (
                    build_public_url(acc.cover_image.bucket, acc.cover_image.object_key)
                    if acc.cover_image else None
                ),                
            })
        
        activities = ActivityService.objects.filter(organization_id=organization).select_related('cover_image')
        for act in activities:
            services.append({
                "service_id": str(act.service_id), "type": "activity", "name": act.name,
                "description": act.description, "price": float(act.price) if act.price else None,
                "price_currency": act.price_currency, "rating": float(act.rating) if act.rating else None,
                "activity_type": act.activity_type, "duration_minutes": act.duration_minutes,
                "guide_included": act.guide_included, "details": act.details,
                "cover_image_url": (
                    build_public_url(act.cover_image.bucket, act.cover_image.object_key)
                    if act.cover_image else None
                ),                
            })
        
        return Response({"services": services}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error en get_user_services: {e}", exc_info=True)
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
    service = get_object_or_404(Model.objects.select_related('cover_image'), pk=service_id)
    
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or service.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para ver este servicio"},
            status=status.HTTP_403_FORBIDDEN,
        )
    
    response_data = {
        "service_id": str(service.service_id), "type": tipo, "name": service.name,
        "description": service.description, "price": float(service.price) if service.price else None,
        "price_currency": service.price_currency, "details": service.details, "policies": service.policies,
        "rating": float(service.rating) if service.rating else None,
        "organization_id": str(service.organization_id.organization_id) if service.organization_id else None,
        "place_id": str(service.place_id.place_id) if service.place_id else None,
        "cover_image": {"public_url": build_public_url(service.cover_image.bucket, service.cover_image.object_key)} if service.cover_image else None,
    }
    
    if tipo == "accommodation":
        response_data.update({
            "accommodation_type": service.accommodation_type, "amenities": service.amenities,
            "beds": service.beds, "capacity": service.capacity,
            "check_in_time": str(service.check_in_time) if service.check_in_time else None,
            "check_out_time": str(service.check_out_time) if service.check_out_time else None,
            "parking": service.parking,
        })
    elif tipo == "transport":
        response_data.update({
            "transport_type": service.transport_type, "schedule": service.schedule, "capacity": service.capacity,
        })
    elif tipo == "activity":
        response_data.update({
            "activity_type": service.activity_type, "duration_minutes": service.duration_minutes, "guide_included": service.guide_included,
        })
    
    return Response(response_data, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_service(request):
    # (Sin cambios)
    service_type = (request.data.get("service_type") or "").lower()
    if service_type not in MODEL_BY_TYPE:
        return Response(
            {"detail": "service_type debe ser uno de: accommodation, transport, activity"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Obtener la organización del usuario autenticado
    try:
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

    allowed = BASE_FIELDS | TYPE_FIELDS[service_type]
    payload = {k: v for k, v in request.data.items() if k in allowed}

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

    cover_image_id   = request.data.get("cover_image_id")
    cover_object_key = request.data.get("cover_object_key")
    cover_public_url = request.data.get("cover_public_url")

    raw_details = payload.get("details")
    if isinstance(raw_details, str):
        try:
            details = json.loads(raw_details)
            if not isinstance(details, dict):
                details = {"text": raw_details}
        except Exception:
            details = {"text": raw_details}
    elif isinstance(raw_details, dict):
        details = raw_details
    else:
        details = {}

    if cover_image_id or cover_object_key or cover_public_url:
        details.setdefault("cover_image", {})
        if cover_image_id:
            details["cover_image"]["id"] = cover_image_id
        if cover_object_key:
            details["cover_image"]["object_key"] = cover_object_key
        if cover_public_url:
            details["cover_image"]["url"] = cover_public_url

    payload["details"] = details   

    Model = MODEL_BY_TYPE[service_type]
    try:
        with transaction.atomic():
            obj = Model.objects.create(**payload)
            cover_image_id = request.data.get("cover_image_id")
            if cover_image_id:
                try:
                    img = Image.objects.get(pk=cover_image_id)
                    obj.cover_image = img
                    obj.save(update_fields=["cover_image"])
                except Image.DoesNotExist:
                    pass
    except (IntegrityError, ValidationError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": f"Error al crear servicio: {e}"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {"service_id": str(getattr(obj, "service_id", obj.pk)), "type": service_type, "name": obj.name,},
        status=status.HTTP_201_CREATED,
    )

@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def update_service(request, service_type: str, service_id: str):
    """
    Actualizar un servicio específico
    """
    print(f"=== UPDATE SERVICE ===")
    
    tipo = (service_type or "").lower()
    if tipo not in MODEL_BY_TYPE:
        return Response(
            {"detail": "service_type debe ser uno de: accommodation, transport, activity"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    Model = MODEL_BY_TYPE[tipo]
    instancia = get_object_or_404(Model.objects.select_related('cover_image'), pk=service_id)
    
    old_image = instancia.cover_image 

    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or instancia.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para editar este servicio"},
            status=status.HTTP_403_FORBIDDEN,
        )

    permitidos = BASE_FIELDS | TYPE_FIELDS[tipo] | {"place_id"}
    incoming = {k: v for k, v in request.data.items() if k in permitidos}
    
    print(f"Campos a actualizar: {list(incoming.keys())}")

    if "place_id" in incoming:
        place_pk = incoming.pop("place_id")
        if place_pk:
            lugar = get_object_or_404(Place, pk=place_pk)
            instancia.place_id = lugar
        else:
            instancia.place_id = None

    for field_name, value in incoming.items():
        print(f"Setting {field_name} = {value} (type: {type(value)})")
        if field_name == "amenities":
            if isinstance(value, str):
                if value.strip():
                    value = [item.strip() for item in value.split(',')]
                else:
                    value = []
            elif isinstance(value, list):
                value = value
            else:
                value = []
            print(f"Processed amenities: {value}")
        setattr(instancia, field_name, value)

    try:
        with transaction.atomic():
            instancia.save()
            print("Servicio actualizado exitosamente (campos base)")

            new_image_id = request.data.get("cover_image_id", "NO_ENVIADO")

            if new_image_id == "NO_ENVIADO":
                print("No se envió 'cover_image_id'. La imagen no se toca.")
                pass
            
            elif new_image_id:
                try:
                    new_image = Image.objects.get(pk=new_image_id)
                    instancia.cover_image = new_image
                    instancia.save(update_fields=["cover_image"])
                    print(f"Imagen de portada actualizada a: {new_image_id}")
                    
                    # Borrar la antigua si era diferente
                    if old_image and old_image.id != new_image.id:
                        print(f"Borrando imagen antigua: {old_image.object_key}")
                        s3 = s3_client()
                        s3.delete_object(Bucket=old_image.bucket, Key=old_image.object_key)
                        old_image.delete()
                        print("Imagen antigua borrada exitosamente.")
                        
                except Image.DoesNotExist:
                    print(f"ADVERTENCIA: Image ID {new_image_id} no encontrado. Ignorando.")

            else:
                print("Se recibió 'cover_image_id' nulo. Borrando imagen.")
                instancia.cover_image = None
                instancia.save(update_fields=["cover_image"])
                
                # Borrar la antigua si existía
                if old_image:
                    print(f"Borrando imagen antigua: {old_image.object_key}")
                    s3 = s3_client()
                    s3.delete_object(Bucket=old_image.bucket, Key=old_image.object_key)
                    old_image.delete()
                    print("Imagen antigua borrada exitosamente.")

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
    servicio = get_object_or_404(Model.objects.select_related('cover_image'), pk=service_id)
    
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or servicio.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para eliminar este servicio"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        old_image = servicio.cover_image
        if old_image:
            print(f"Borrando imagen asociada: {old_image.object_key}")
            try:
                s3 = s3_client()
                s3.delete_object(Bucket=old_image.bucket, Key=old_image.object_key)
                old_image.delete()
                print("Imagen asociada borrada exitosamente.")
            except Exception as e:
                logger.error(f"Error al borrar imagen asociada {old_image.id} de S3: {e}", exc_info=True)

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
    
EVENT_BASE_FIELDS = {
    "name", "description", "price", "price_currency", "details", "rating", "is_featured"
}
EVENT_SPECIFIC_FIELDS = {"start_date", "end_date"}
EVENT_ALLOWED = EVENT_BASE_FIELDS | EVENT_SPECIFIC_FIELDS | {"place_id"}
EVENT_REQUIRED = {"name", "start_date", "end_date", "price", "price_currency"}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_events(request):
    """
    Obtener todos los eventos de la organización a la que pertenece el usuario
    (sin filtros adicionales, siguiendo el patrón de services).
    """
    try:
        organization_user_relation = OrganizationUser.objects.filter(user_id=request.user).first()
        if not organization_user_relation:
            print("ERROR: No se encontró OrganizationUser")
            return Response(
                {"detail": "El usuario no pertenece a ninguna organización"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        organization = organization_user_relation.organization_id
        
        events_queryset = Event.objects.filter(organization_id=organization).select_related('cover_image')
        print(f"Eventos encontrados: {events_queryset.count()}")

        events_payload = []
        for event_instance in events_queryset:
            events_payload.append({
                "event_id": str(event_instance.event_id),
                "name": event_instance.name,
                "description": event_instance.description,
                "start_date": event_instance.start_date.isoformat() if event_instance.start_date else None,
                "end_date": event_instance.end_date.isoformat() if event_instance.end_date else None,
                "price": float(event_instance.price) if event_instance.price else None,
                "price_currency": event_instance.price_currency,
                "rating": float(event_instance.rating) if event_instance.rating is not None else None,
                "details": event_instance.details,
                "is_featured": bool(event_instance.is_featured),
                "organization_id": str(event_instance.organization_id.organization_id) if event_instance.organization_id else None,
                "place_id": str(event_instance.place_id.place_id) if event_instance.place_id else None,
                "cover_image_url": (
                    build_public_url(event_instance.cover_image.bucket, event_instance.cover_image.object_key)
                    if event_instance.cover_image else None
                ),
            })
        return Response({"events": events_payload}, status=status.HTTP_200_OK)
    except Exception as error:
        print(f"EXCEPCIÓN: {str(error)}")
        import traceback
        traceback.print_exc()
        return Response({"detail": f"Error al obtener eventos: {str(error)}"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_event_detail(request, event_id: str):
    """
    Obtener detalles de un evento específico
    """
    event_instance = get_object_or_404(Event.objects.select_related('cover_image'), pk=event_id)

    organization_user_relation = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user_relation or event_instance.organization_id != organization_user_relation.organization_id:
        print("ERROR: Permisos insuficientes para ver el evento")
        return Response(
            {"detail": "No tienes permisos para ver este evento"},
            status=status.HTTP_403_FORBIDDEN,
        )

    response_data = {
        "event_id": str(event_instance.event_id),
        "name": event_instance.name,
        "description": event_instance.description,
        "start_date": event_instance.start_date.isoformat() if event_instance.start_date else None,
        "end_date": event_instance.end_date.isoformat() if event_instance.end_date else None,
        "price": float(event_instance.price) if event_instance.price is not None else None,
        "price_currency": event_instance.price_currency,
        "details": event_instance.details,
        "is_featured": bool(event_instance.is_featured),
        "rating": float(event_instance.rating) if event_instance.rating is not None else None,
        "organization_id": str(event_instance.organization_id.organization_id) if event_instance.organization_id else None,
        "place_id": str(event_instance.place_id.place_id) if event_instance.place_id else None,
        "cover_image": {"public_url": build_public_url(event_instance.cover_image.bucket, event_instance.cover_image.object_key)} if event_instance.cover_image else None,
    }
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_event(request):
    """
    Crear un evento para la organización del usuario.
    Requeridos: name, start_date, end_date, price, price_currency
    Opcionales: description, details (JSON), is_featured, rating, place_id
    """
    try:
        organization_user_relation = OrganizationUser.objects.filter(user_id=request.user).first()
        if not organization_user_relation:
            return Response(
                {"detail": "El usuario no pertenece a ninguna organización"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        organization = organization_user_relation.organization_id
        
        place_instance = None
        place_id_param = request.data.get("place_id")
        if place_id_param:
            place_instance = get_object_or_404(Place, pk=place_id_param)

        payload = {field: value for field, value in request.data.items() if field in EVENT_ALLOWED}

        missing_fields = [field for field in EVENT_REQUIRED if payload.get(field) in (None, "")]
        if missing_fields:
            print(f"Faltan: {missing_fields}")
            return Response(
                {"detail": "Faltan campos requeridos", "fields": sorted(set(missing_fields))},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload["organization_id"] = organization
        payload["place_id"] = place_instance

        with transaction.atomic():
            event_created = Event.objects.create(**payload)
            print(f"Evento creado: {event_created.event_id} - {event_created.name}")
        
        cover_image_id = request.data.get("cover_image_id")
        if cover_image_id:
            try:
                img = Image.objects.get(pk=cover_image_id)
                event_created.cover_image = img
                event_created.save(update_fields=["cover_image"])
            except Image.DoesNotExist:
                pass

        return Response(
            {"event_id": str(event_created.event_id), "name": event_created.name},
            status=status.HTTP_201_CREATED,
        )

    except (IntegrityError, ValidationError) as creation_error:
        return Response({"detail": str(creation_error)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as unexpected_error:
        return Response({"detail": f"Error al crear evento: {unexpected_error}"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def update_event(request, event_id: str):
    """
    Actualizar un evento específico
    """
    
    event_instance = get_object_or_404(Event.objects.select_related('cover_image'), pk=event_id)
    
    old_image = event_instance.cover_image

    organization_user_relation = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user_relation or event_instance.organization_id != organization_user_relation.organization_id:
        return Response(
            {"detail": "No tienes permisos para editar este evento"},
            status=status.HTTP_403_FORBIDDEN,
        )

    fields_to_update = {field: value for field, value in request.data.items() if field in EVENT_ALLOWED}
    print(f"Campos a actualizar: {list(fields_to_update.keys())}")

    if "place_id" in fields_to_update:
        place_id_param = fields_to_update.pop("place_id")
        if place_id_param:
            event_instance.place_id = get_object_or_404(Place, pk=place_id_param)
        else:
            event_instance.place_id = None

    for field_name, field_value in fields_to_update.items():
        print(f"Setting {field_name} = {field_value} (type: {type(field_value)})")
        setattr(event_instance, field_name, field_value)

    try:
        with transaction.atomic():
            event_instance.save()
            print("Evento actualizado exitosamente")
            
            new_image_id = request.data.get("cover_image_id", "NO_ENVIADO")

            if new_image_id == "NO_ENVIADO":
                print("No se envió 'cover_image_id'. La imagen no se toca.")
                pass
            
            elif new_image_id:
                try:
                    new_image = Image.objects.get(pk=new_image_id)
                    event_instance.cover_image = new_image # 'instancia' es un alias de 'event_instance'
                    event_instance.save(update_fields=["cover_image"])
                    print(f"Imagen de portada actualizada a: {new_image_id}")
                    
                    if old_image and old_image.id != new_image.id:
                        print(f"Borrando imagen antigua: {old_image.object_key}")
                        s3 = s3_client()
                        s3.delete_object(Bucket=old_image.bucket, Key=old_image.object_key)
                        old_image.delete()
                        print("Imagen antigua borrada exitosamente.")
                        
                except Image.DoesNotExist:
                    print(f"ADVERTENCIA: Image ID {new_image_id} no encontrado. Ignorando.")

            else:
                print("Se recibió 'cover_image_id' nulo. Borrando imagen.")
                event_instance.cover_image = None
                event_instance.save(update_fields=["cover_image"])
                
                if old_image:
                    print(f"Borrando imagen antigua: {old_image.object_key}")
                    s3 = s3_client()
                    s3.delete_object(Bucket=old_image.bucket, Key=old_image.object_key)
                    old_image.delete()
                    print("Imagen antigua borrada exitosamente.")

    except Exception as update_error:
        print(f"Error durante la actualización: {str(update_error)}")
        import traceback
        traceback.print_exc()
        return Response({"detail": str(update_error)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "event_id": str(event_instance.event_id),
            "name": event_instance.name,
            "updated_fields": list(fields_to_update.keys()),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_event(request, event_id: str):
    """
    Eliminar un evento
    """
    event_instance = get_object_or_404(Event.objects.select_related('cover_image'), pk=event_id)

    organization_user_relation = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user_relation or event_instance.organization_id != organization_user_relation.organization_id:
        return Response(
            {"detail": "No tienes permisos para eliminar este evento"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        old_image = event_instance.cover_image
        if old_image:
            print(f"Borrando imagen asociada: {old_image.object_key}")
            try:
                s3 = s3_client()
                s3.delete_object(Bucket=old_image.bucket, Key=old_image.object_key)
                old_image.delete()
                print("Imagen asociada borrada exitosamente.")
            except Exception as e:
                logger.error(f"Error al borrar imagen asociada {old_image.id} de S3: {e}", exc_info=True)

        event_instance.delete()
        return Response({"detail": "Evento eliminado correctamente"}, status=status.HTTP_200_OK)
    except Exception as delete_error:
        return Response({"detail": f"Error al eliminar evento: {delete_error}"}, status=status.HTTP_400_BAD_REQUEST)