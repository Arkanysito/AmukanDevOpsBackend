# apps/recommendation/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from .services import recommend_places

from .serializers import (
    PlaceRecoSerializer, 
    ActivityServiceRecoSerializer, 
    EventRecoSerializer
)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommend_places_view(request):
    try:
        service_type = request.GET.get('type', 'place')
        zone_id = request.GET.get('zone_id')
        
        zone = None
        if zone_id:
            from apps.location.models import Zone
            try:
                zone = Zone.objects.get(zone_id=zone_id)
            except Zone.DoesNotExist:
                pass
        
        recommendations = recommend_places(
            user=request.user, 
            service_type=service_type, 
            zone=zone, 
            top_k=10
        )
        
        data = []
        for place, score in recommendations:
            serializer = PlaceRecoSerializer(place, context={'score': score})
            data.append(serializer.data)
            
        return Response(data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommend_services_view(request):
    """
    Vista de recomendación genérica que despacha al serializer correcto
    basado en el service_type.
    """
    
    # Mapeo de service_type al Serializer correcto
    SERIALIZER_MAP = {
        'accommodation': PlaceRecoSerializer,
        'activity': ActivityServiceRecoSerializer,
        'event': EventRecoSerializer,
        'restaurant': PlaceRecoSerializer,
        'place': PlaceRecoSerializer,
    }
    
    try:
        service_type = request.GET.get('type')
        if not service_type or service_type not in SERIALIZER_MAP:
            return JsonResponse({"error": "Invalid or missing 'type' parameter"}, status=400)
        
        zone_id = request.GET.get('zone_id')
        zone = None
        if zone_id:
            from apps.location.models import Zone
            try:
                zone = Zone.objects.get(zone_id=zone_id)
            except Zone.DoesNotExist:
                pass
        
        # 1. Llamar al MISMO service de siempre
        recommendations = recommend_places(
            user=request.user, 
            service_type=service_type, 
            zone=zone, 
            top_k=100
        )
        
        # 2. Elegir el Serializer CORRECTO del map
        SerializerClass = SERIALIZER_MAP[service_type]
        
        # 3. Serializar los datos
        data = []
        for service_object, score in recommendations:
            # Pasa el 'score' al serializer a través del contexto
            serializer = SerializerClass(service_object, context={'score': score})
            data.append(serializer.data)
            
        return Response(data)
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)