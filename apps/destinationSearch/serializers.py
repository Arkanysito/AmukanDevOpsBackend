from rest_framework import serializers
from apps.experiences.models import AccommodationService, ActivityService, Event
from apps.location.models import Place
# Reemplaza 'tu_app.utils.storage' con la ubicación real de tu función build_public_url
from apps.core.s3_utils import build_public_url

# --- FUNCIÓN DE UTILIDAD COMPARTIDA ---
def get_cover_image_url(self, obj):
    """Calcula y devuelve la URL pública de la imagen de portada."""
    # Se asume que obj.cover_image es un objeto con bucket y object_key,
    # o es None si no hay imagen.
    if obj.cover_image:
        return build_public_url(obj.cover_image.bucket, obj.cover_image.object_key)
    return None

# ----------------------------------------------------------------------
# 🏨 AccommodationServiceSerializer
# ----------------------------------------------------------------------

class AccommodationServiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)
    cover_image_url = serializers.SerializerMethodField() # <-- Campo Agregado

    class Meta:
        model = AccommodationService
        fields = [
            'service_id',
            'name',
            'organization_name',
            'description',
            'price',
            'beds',
            'capacity',
            'check_in_time',
            'check_out_time',
            'place_coordinates',
            'cover_image_url', # <-- Añadir
        ]
    
    get_cover_image_url = get_cover_image_url # <-- Usar la función utilitaria


# ----------------------------------------------------------------------
# 🍽️ PlaceAccommodationSerializer (Para lugares usados como alojamiento)
# ----------------------------------------------------------------------

class PlaceAccommodationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    price = serializers.DecimalField(source='average_price', max_digits=8, decimal_places=2, read_only=True)
    place_coordinates = serializers.CharField(source='coordinates', read_only=True)
    cover_image_url = serializers.SerializerMethodField() # <-- Campo Agregado
    
    # Campos por defecto
    beds = serializers.IntegerField(default=2, read_only=True)
    capacity = serializers.IntegerField(default=2, read_only=True)
    check_in_time = serializers.TimeField(default="14:00", read_only=True)
    check_out_time = serializers.TimeField(default="12:00", read_only=True)

    class Meta:
        model = Place
        fields = [
            'place_id',
            'name',
            'organization_name',
            'description',
            'price',
            'beds',
            'capacity',
            'check_in_time',
            'check_out_time',
            'place_coordinates',
            'type',
            'rating',
            'cover_image_url', # <-- Añadir
        ]
    
    get_cover_image_url = get_cover_image_url # <-- Usar la función utilitaria


# ----------------------------------------------------------------------
# 🎯 ActivityServiceSerializer
# ----------------------------------------------------------------------

class ActivityServiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)
    cover_image_url = serializers.SerializerMethodField() # <-- Campo Agregado

    class Meta:
        model = ActivityService
        fields = [
            'service_id',
            'name',
            'organization_name',
            'description',
            'price',
            'place_coordinates',
            'cover_image_url', # <-- Añadir
        ]
    
    get_cover_image_url = get_cover_image_url # <-- Usar la función utilitaria


# ----------------------------------------------------------------------
# 🎉 EventSerializer
# ----------------------------------------------------------------------

class EventSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)
    cover_image_url = serializers.SerializerMethodField() # <-- Campo Agregado

    class Meta:
        model = Event
        fields = [
            'event_id',
            'name', 
            'organization_name', 
            'description', 
            'start_date', 
            'end_date', 
            'price', 
            'place_coordinates',
            'cover_image_url', # <-- Añadir
        ]
    
    get_cover_image_url = get_cover_image_url # <-- Usar la función utilitaria


# ----------------------------------------------------------------------
# ☕ PlaceSerializer (Para gastronomía/lugares en general)
# ----------------------------------------------------------------------

class PlaceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    cover_image_url = serializers.SerializerMethodField() # <-- Campo Agregado

    class Meta:
        model = Place
        fields = [
            'place_id',
            'name',
            'organization_name',
            'coordinates',
            'type',
            'average_price',
            'cover_image_url', # <-- Añadir
        ]
    
    get_cover_image_url = get_cover_image_url # <-- Usar la función utilitaria