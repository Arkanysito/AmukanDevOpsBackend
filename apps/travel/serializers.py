# apps/travel/serializers.py
from rest_framework import serializers
from apps.travel.models import Itinerary, ItineraryItem, ItineraryCollaborator
from apps.experiences.models import Event, AccommodationService, ActivityService
from apps.location.models import Place
from django.contrib.contenttypes.models import ContentType

class ItineraryItemDetailSerializer(serializers.ModelSerializer):
    service_name = serializers.SerializerMethodField()
    service_type = serializers.SerializerMethodField()
    direccion = serializers.SerializerMethodField()
    coordenadas = serializers.SerializerMethodField()
    
    class Meta:
        model = ItineraryItem
        fields = [
            'item_id', 'scheduled_date', 'estimated_cost', 'estimated_cost_currency',
            'service_name', 'service_type', 'direccion', 'coordenadas'
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
        """Obtiene la dirección - como no usamos address, generamos una basada en coordenadas"""
        try:
            coordenadas = self.get_coordenadas(obj)
            if coordenadas:
                return f"Ubicación: {coordenadas.get('lat', 'N/A')}, {coordenadas.get('lng', 'N/A')}"
            
            # Si no hay coordenadas, usar el nombre del servicio
            service_name = self.get_service_name(obj)
            return f"{service_name} - Ubicación no especificada"
                        
        except Exception as e:
            print(f"Error obteniendo dirección: {e}")
        return 'Ubicación no disponible'
    
    def get_coordenadas(self, obj):
        """Obtiene las coordenadas del servicio - VERSIÓN SIMPLIFICADA"""
        try:
            # Método 1: Usar el objeto relacionado directamente
            if obj.reservable:
                return self._extraer_coordenadas_desde_objeto(obj.reservable)
            
            # Método 2: Buscar manualmente el objeto
            model_class = obj.content_type.model_class()
            if model_class:
                service_obj = model_class.objects.filter(
                    **{f'{obj.content_type.model}_id': obj.object_id}
                ).first()
                if service_obj:
                    return self._extraer_coordenadas_desde_objeto(service_obj)
                    
        except Exception as e:
            print(f"Error obteniendo coordenadas: {e}")
        
        return None
    
    def _extraer_coordenadas_desde_objeto(self, service_obj):
        """Extrae coordenadas de cualquier objeto de servicio"""
        if not service_obj:
            return None
            
        try:
            # CASO 1: El servicio ES un Place (comida)
            if isinstance(service_obj, Place):
                if hasattr(service_obj, 'coordinates') and service_obj.coordinates:
                    return self._formatear_coordenadas(service_obj.coordinates)
            
            # CASO 2: El servicio TIENE un Place (hospedaje, actividades, transporte, eventos)
            elif hasattr(service_obj, 'place_id') and service_obj.place_id:
                place = service_obj.place_id
                if hasattr(place, 'coordinates') and place.coordinates:
                    return self._formatear_coordenadas(place.coordinates)
            
            # CASO 3: El servicio tiene coordenadas directas (por si acaso)
            elif hasattr(service_obj, 'coordinates') and service_obj.coordinates:
                return self._formatear_coordenadas(service_obj.coordinates)
                
        except Exception as e:
            print(f"Error extrayendo coordenadas: {e}")
        
        return None
    
    def _formatear_coordenadas(self, coordinates):
        """Formatea las coordenadas para el frontend"""
        try:
            # Para Django GIS PointField - el formato más común
            if hasattr(coordinates, 'x') and hasattr(coordinates, 'y'):
                return {
                    'lat': float(coordinates.y),
                    'lng': float(coordinates.x)
                }
            
            # Para string WKT "POINT(lng lat)"
            elif hasattr(coordinates, 'wkt'):
                import re
                wkt_string = str(coordinates.wkt)
                match = re.match(r'POINT\(\s*([-\d.]+)\s+([-\d.]+)\s*\)', wkt_string)
                if match:
                    lng, lat = match.groups()
                    return {
                        'lat': float(lat),
                        'lng': float(lng)
                    }
            
            # Si ya es un dict con las keys correctas
            elif isinstance(coordinates, dict):
                if 'lat' in coordinates and 'lng' in coordinates:
                    return coordinates
                elif 'latitude' in coordinates and 'longitude' in coordinates:
                    return {
                        'lat': coordinates['latitude'],
                        'lng': coordinates['longitude']
                    }
                    
        except Exception as e:
            print(f"Error formateando coordenadas: {e}")
            print(f"Tipo de coordenadas: {type(coordinates)}")
            print(f"Valor de coordenadas: {coordinates}")
        
        return None

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