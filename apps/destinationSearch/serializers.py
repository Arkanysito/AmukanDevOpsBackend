from rest_framework import serializers
from apps.experiences.models import AccommodationService, ActivityService, Event, TransportService

class AccommodationServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccommodationService
        fields = ['name', 'description', 'price', 'beds', 'room_capacity']

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

