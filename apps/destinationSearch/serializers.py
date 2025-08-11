from rest_framework import serializers
from apps.experiences.models import AccommodationService, ActivityService, Event, TransportService

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
    class Meta:
        model = ActivityService
        fields = ['name', 'description', 'price']

class TransportServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportService
        fields = ['name','description','price','transport_type', 'schedule', 'capacity']

class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['name', 'description', 'start_date', 'end_date', 'price']

