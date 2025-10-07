from rest_framework import serializers
from apps.travel.models import Itinerary, ItineraryItem, ItineraryCollaborator
from apps.booking.models import Reservation

class ItineraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItineraryItem
        fields = '__all__'

class ItinerarySerializer(serializers.ModelSerializer):
    items = ItineraryItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Itinerary
        fields = ['itinerary_id', 'name', 'created_at', 'is_shared', 'items']