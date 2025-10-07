# apps/travel/serializers.py
from rest_framework import serializers
from apps.travel.models import Itinerary, ItineraryItem, ItineraryCollaborator
from apps.experiences.models import Event, AccommodationService, ActivityService, TransportService
from apps.location.models import Place
from django.contrib.contenttypes.models import ContentType

class ItineraryItemDetailSerializer(serializers.ModelSerializer):
    service_name = serializers.SerializerMethodField()
    service_type = serializers.SerializerMethodField()
    direccion = serializers.SerializerMethodField()
    hora = serializers.SerializerMethodField()
    
    class Meta:
        model = ItineraryItem
        fields = [
            'item_id', 'scheduled_date', 'estimated_cost', 'estimated_cost_currency',
            'service_name', 'service_type', 'direccion', 'hora'
        ]
    
    def get_service_name(self, obj):
        """Obtiene el nombre del servicio"""
        try:
            if obj.reservable:
                return getattr(obj.reservable, 'name', 'Servicio sin nombre')
            
            # Fallback: intentar obtener el objeto manualmente
            model_class = obj.content_type.model_class()
            if model_class:
                service_obj = model_class.objects.filter(
                    **{f'{obj.content_type.model}_id': obj.object_id}
                ).first()
                if service_obj:
                    return getattr(service_obj, 'name', 'Servicio sin nombre')
                    
        except Exception as e:
            print(f"Error obteniendo service_name: {e}")
        return 'Servicio no disponible'
    
    def get_service_type(self, obj):
        return obj.content_type.model
    
    def get_direccion(self, obj):
        """Obtiene la dirección del servicio"""
        try:
            if obj.reservable:
                # Para servicios que tienen place_id
                if hasattr(obj.reservable, 'place_id') and obj.reservable.place_id:
                    return getattr(obj.reservable.place_id, 'address', 'Dirección no disponible')
                # Para Place directamente
                elif hasattr(obj.reservable, 'address'):
                    return obj.reservable.address
            
            # Fallback manual
            model_class = obj.content_type.model_class()
            if model_class:
                service_obj = model_class.objects.filter(
                    **{f'{obj.content_type.model}_id': obj.object_id}
                ).first()
                if service_obj:
                    if hasattr(service_obj, 'place_id') and service_obj.place_id:
                        return getattr(service_obj.place_id, 'address', 'Dirección no disponible')
                    elif hasattr(service_obj, 'address'):
                        return service_obj.address
                        
        except Exception as e:
            print(f"Error obteniendo dirección: {e}")
        return 'Dirección no disponible'
    
    def get_hora(self, obj):
        """Formatea la hora para el frontend"""
        if obj.scheduled_date:
            return obj.scheduled_date.strftime('%H:%M')
        return '--:--'

class ItinerarySerializer(serializers.ModelSerializer):
    items = ItineraryItemDetailSerializer(many=True, read_only=True, source='itineraryitem_set')
    
    class Meta:
        model = Itinerary
        fields = ['itinerary_id', 'name', 'created_at', 'is_shared', 'items']

class ItineraryWithItemsSerializer(serializers.ModelSerializer):
    items = ItineraryItemDetailSerializer(many=True, read_only=True, source='itineraryitem_set')
    collaborators = serializers.SerializerMethodField()
    
    class Meta:
        model = Itinerary
        fields = ['itinerary_id', 'name', 'created_at', 'is_shared', 'items', 'collaborators']
    
    def get_collaborators(self, obj):
        collaborators = ItineraryCollaborator.objects.filter(itinerary_id=obj)
        return [{
            'username': collab.user_id.username,
            'role': collab.role
        } for collab in collaborators]