# apps/location/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import Point

from apps.organizations.models import OrganizationUser
from apps.location.models import Place, Zone
from django.contrib.gis.geos import Point

# Campos permitidos que pueden llegar desde el frontend para un Place
PLACE_ALLOWED_FIELDS = {
    "name",
    "description",
    "address",
    "type",
    "coordinates", # Se espera un dict GeoJSON: {"type": "Point", "coordinates": [long, lat]}
    "accessibility_features", # Se espera un dict/JSON
    "average_price",
    "schedule", # Se espera un dict/JSON
    "zone_id", # FK
}


@api_view(["GET"])
@permission_classes([AllowAny]) # O IsAuthenticated
def list_zones(request):
    """
    Obtener una lista de todas las Zonas
    """
    try:
        # Ordenamos por nombre para que el dropdown se vea bien
        zones = Zone.objects.all().order_by('name') 
        
        response_data = []
        for z in zones:
            response_data.append({
                "zone_id": str(z.zone_id),
                "name": z.name,
                "level": z.get_level_display() # Muestra el label (ej: "Comuna")
            })
        
        # El frontend espera el JSON dentro de una clave "data"
        return Response({"data": response_data}, status=status.HTTP_200_OK) 

    except Exception as e:
        print(f"Error al listar zonas: {str(e)}")
        return Response({"detail": f"Error al listar zonas: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_places(request):
    """
    Obtener todos los Places (Gastronomía, etc.)
    asignados a la organización del usuario.
    """
    try:
        organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
        if not organization_user:
            return Response(
                {"detail": "El usuario no pertenece a ninguna organización"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        organization = organization_user.organization_id
        
        # Filtramos los Places por la organización del usuario
        places = Place.objects.filter(organization_id=organization)
        
        # Serializamos los datos (similar a get_place_detail)
        response_data = []
        for place in places:
            response_data.append({
                "place_id": str(place.place_id),
                "name": place.name,
                "description": place.description,
                "address": place.address,
                "type": place.type, # Ej: 'RESTAURANT', 'CAFE'
                "coordinates": {
                    "type": "Point",
                    "coordinates": [place.coordinates.x, place.coordinates.y]
                } if place.coordinates else None,
                "accessibility_features": place.accessibility_features,
                "average_price": float(place.average_price) if place.average_price is not None else None,
                "schedule": place.schedule,
                "rating": float(place.rating) if place.rating is not None else None,
                "organization_id": str(place.organization_id.organization_id) if place.organization_id else None,
                "zone_id": str(place.zone_id.zone_id) if place.zone_id else None,
            })
        
        return Response({"places": response_data}, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error al listar lugares: {str(e)}")
        return Response({"detail": f"Error al listar lugares: {e}"}, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_place(request):
    """
    Crear un nuevo Place (para Gastronomía, etc.)
    Asignado a la organización del usuario.
    """

    try:
        organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
        if not organization_user:
            return Response(
                {"detail": "El usuario no pertenece a ninguna organización"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        organization = organization_user.organization_id

        payload = {k: v for k, v in request.data.items() if k in PLACE_ALLOWED_FIELDS}

        # Validación de requeridos
        required = {"name", "description", "type", "coordinates"}
        missing = [f for f in required if payload.get(f) in (None, "")]
        if missing:
             return Response(
                {"detail": "Faltan campos requeridos", "fields": sorted(missing)},
                status=status.HTTP_400_BAD_REQUEST,
            )
      
        # 1. Zone (FK)
        if "zone_id" in payload:
            zone_pk = payload.pop("zone_id")
            if zone_pk:
                payload["zone_id"] = get_object_or_404(Zone, pk=zone_pk)
            else:
                payload["zone_id"] = None
        
        # 2. Coordinates (GeoDjango Point)
        coords_data = payload.pop("coordinates", None)
        if coords_data and coords_data.get("type") == "Point" and coords_data.get("coordinates"):
            try:
                # GeoJSON es [longitud, latitud]
                lon, lat = coords_data["coordinates"]
                payload["coordinates"] = Point(float(lon), float(lat), srid=4326)
            except (TypeError, ValueError, IndexError):
                 return Response({"detail": "Formato de 'coordinates' inválido"}, status=status.HTTP_400_BAD_REQUEST)
        else:
             return Response({"detail": "Campo 'coordinates' es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        # Asignar organización
        payload["organization_id"] = organization

        with transaction.atomic():
            place = Place.objects.create(**payload)
            print(f"Place creado: {place.place_id}")

        return Response(
            {
                "place_id": str(place.place_id),
                "name": place.name,
            },
            status=status.HTTP_201_CREATED,
        )

    except (IntegrityError, ValidationError) as e:
        print(f"Error de validación: {str(e)}")
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"detail": f"Error al crear lugar: {e}"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_place_detail(request, place_id: str):
    """
    Obtener detalles de un Place específico.
    Usado por la vista 'EditarMiComercio' para 'Gastronomía'.
    """
    print(f"=== GET PLACE DETAIL ===")
    print(f"Place ID: {place_id}")
    
    place = get_object_or_404(Place, pk=place_id)
    
    # Verificar permisos (si el Place tiene organización)
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if place.organization_id:
        if not organization_user or place.organization_id != organization_user.organization_id:
            return Response(
                {"detail": "No tienes permisos para ver este lugar"},
                status=status.HTTP_403_FORBIDDEN,
            )
    # (Si no tiene org, podría ser un lugar público, pero para editar, asumimos que debe tener org)
    elif not organization_user:
         return Response(
            {"detail": "No tienes permisos para ver este lugar"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Serializar datos
    response_data = {
        "place_id": str(place.place_id),
        "name": place.name,
        "description": place.description,
        "address": place.address,
        "type": place.type,
        "coordinates": { # Convertir Point a GeoJSON
            "type": "Point",
            "coordinates": [place.coordinates.x, place.coordinates.y] # [long, lat]
        } if place.coordinates else None,
        "accessibility_features": place.accessibility_features,
        "average_price": float(place.average_price) if place.average_price is not None else None,
        "schedule": place.schedule,
        "rating": float(place.rating) if place.rating is not None else None,
        "organization_id": str(place.organization_id.organization_id) if place.organization_id else None,
        "zone_id": str(place.zone_id.zone_id) if place.zone_id else None,
    }
    
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def update_place(request, place_id: str):
    """
    Actualizar un Place (Gastronomía)
    """
    print(f"=== UPDATE PLACE ===")
    print(f"Place ID: {place_id}")
    print(f"User: {request.user}")
    print(f"Request Data: {request.data}")
    
    instancia = get_object_or_404(Place, pk=place_id)
    
    # Verificar permisos
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or instancia.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para editar este lugar"},
            status=status.HTTP_403_FORBIDDEN,
        )

    incoming = {k: v for k, v in request.data.items() if k in PLACE_ALLOWED_FIELDS}
    print(f"Campos a actualizar: {list(incoming.keys())}")

    try:
        with transaction.atomic():            
            # 1. Zone (FK)
            if "zone_id" in incoming:
                zone_pk = incoming.pop("zone_id")
                if zone_pk:
                    instancia.zone_id = get_object_or_404(Zone, pk=zone_pk)
                else:
                    instancia.zone_id = None
            
            # 2. Coordinates (GeoDjango Point)
            coords_data = incoming.pop("coordinates", None)
            if coords_data:
                if coords_data.get("type") == "Point" and coords_data.get("coordinates"):
                    try:
                        lon, lat = coords_data["coordinates"]
                        instancia.coordinates = Point(float(lon), float(lat), srid=4326)
                    except (TypeError, ValueError, IndexError):
                        raise ValidationError("Formato de 'coordinates' inválido")
                else:
                     raise ValidationError("Formato de 'coordinates' inválido")

            # Asignar el resto de campos
            for field_name, value in incoming.items():
                print(f"Setting {field_name} = {value}")
                setattr(instancia, field_name, value)
            
            instancia.save()
            print("Lugar actualizado exitosamente")
            
    except (ValidationError, Exception) as e:
        print(f"Error durante la actualización: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "place_id": str(instancia.place_id),
            "name": instancia.name,
            "updated_fields": list(incoming.keys()),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_place(request, place_id: str):
    """
    Eliminar un Place (Gastronomía)
    """
    place = get_object_or_404(Place, pk=place_id)
    
    # Verificar permisos
    organization_user = OrganizationUser.objects.filter(user_id=request.user).first()
    if not organization_user or place.organization_id != organization_user.organization_id:
        return Response(
            {"detail": "No tienes permisos para eliminar este lugar"},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        place.delete()
        return Response(
            {"detail": "Lugar eliminado correctamente"},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"detail": f"Error al eliminar lugar: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
@api_view(["GET"])
@permission_classes([IsAuthenticated]) # Asegura que el usuario esté logueado
def get_info_from_coords(request):
    """
    Recibe lat/lng y devuelve la Zona de PostGIS que contiene ese punto.
    """
    try:
        # El frontend enviará 'lat' y 'lng' como query params
        lat = float(request.query_params.get('lat'))
        lng = float(request.query_params.get('lng'))
        
        # PostGIS usa (longitud, latitud)
        point = Point(lng, lat, srid=4326)

        # La consulta de PostGIS: busca la Zona cuyo polígono 'coordinates' contiene el punto
        zona = Zone.objects.filter(coordinates__contains=point).first()

        if not zona:
            return Response(
                {"detail": "Punto fuera de las zonas registradas"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Devolvemos los datos de la zona encontrada
        return Response({
            "zone_id": str(zona.zone_id),
            "zone_name": zona.name,
        }, status=status.HTTP_200_OK)

    except (TypeError, ValueError, AttributeError):
        return Response({"detail": "Coordenadas 'lat' y 'lng' inválidas o faltantes"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)