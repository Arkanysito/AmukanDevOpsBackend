from rest_framework import serializers
from apps.experiences.models import AccommodationService, ActivityService, Event, TransportService
from apps.location.models import Place

class AccommodationServiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)

    class Meta:
        model = AccommodationService
        fields = [
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

class ActivityServiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)

    class Meta:
        model = ActivityService
        fields = [
            'name',
            'organization_name',
            'description',
            'price',
            'place_coordinates'
        ]

class TransportServiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)
    class Meta:
        model = TransportService
        fields = [
            'name', 
            'organization_name', 
            'place_coordinates',
            'description', 
            'price',
            'transport_type',  
            'capacity'
        ]

class EventSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization_id.name', read_only=True)
    place_coordinates = serializers.CharField(source='place_id.coordinates', read_only=True)
    class Meta:
        model = Event
        fields = [
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
            'name',
            'organization_name',
            'coordinates',
            'type'
        ]
