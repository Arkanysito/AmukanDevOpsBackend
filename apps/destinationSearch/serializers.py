from rest_framework import serializers
from apps.experiences.models import AccommodationService, ActivityService, Event
from apps.location.models import Place

class AccommodationServiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)

    class Meta:
        model = AccommodationService
        fields = [
            'service_id',
            'name',
            'organization_name',
            'description',
            'price',
            'beds',
            'room_capacity',
            'check_in_time',
            'check_out_time',
            'place_coordinates'
        ]

# NUEVO SERIALIZER para alojamientos basados en Place
class PlaceAccommodationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    # Campos que simulan los de AccommodationService para mantener compatibilidad
    price = serializers.DecimalField(source='average_price', max_digits=8, decimal_places=2, read_only=True)
    place_coordinates = serializers.CharField(source='coordinates', read_only=True)
    
    # Campos por defecto para alojamientos (ya que Place no los tiene)
    beds = serializers.IntegerField(default=2, read_only=True)
    room_capacity = serializers.IntegerField(default=2, read_only=True)
    check_in_time = serializers.TimeField(default="14:00", read_only=True)
    check_out_time = serializers.TimeField(default="12:00", read_only=True)

    class Meta:
        model = Place
        fields = [
            'place_id',
            'name',
            'organization_name',
            'description',
            'price',  # Mapeado de average_price
            'beds',   # Valor por defecto
            'room_capacity',  # Valor por defecto
            'check_in_time',  # Valor por defecto
            'check_out_time', # Valor por defecto
            'place_coordinates',  # Mapeado de coordinates
            'type',   # Tipo de alojamiento (hotel, hostel, etc.)
            'rating'  # Rating del lugar
        ]

class ActivityServiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)

    class Meta:
        model = ActivityService
        fields = [
            'service_id',
            'name',
            'organization_name',
            'description',
            'price',
            'place_coordinates'
        ]

class EventSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)
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
            'place_coordinates'
        ]

class PlaceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)

    class Meta:
        model = Place
        fields = [
            'place_id',
            'name',
            'organization_name',
            'coordinates',
            'type',
            'average_price'
        ]