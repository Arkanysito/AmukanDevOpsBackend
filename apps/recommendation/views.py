# En tu views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from .services import recommend_places  # función existente
from .serializers import PlaceRecoSerializer  # nuevo serializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommend_places_view(request):
    try:
        # Llamar a la función existente con los parámetros adecuados
        # Asumiendo que necesitas especificar un tipo de servicio
        service_type = request.GET.get('type', 'place')  # tipo por defecto
        zone_id = request.GET.get('zone_id')  # opcional
        
        # Obtener la zona si se proporciona zone_id
        zone = None
        if zone_id:
            from apps.location.models import Zone
            try:
                zone = Zone.objects.get(zone_id=zone_id)
            except Zone.DoesNotExist:
                pass
        
        # Llamar a la función de recomendación
        recommendations = recommend_places(
            user=request.user, 
            service_type=service_type, 
            zone=zone, 
            top_k=10
        )
        
        # Usar el serializer para formatear la respuesta
        data = []
        for place, score in recommendations:
            # Pasar el score al serializer a través del contexto
            serializer = PlaceRecoSerializer(place, context={'score': score})
            data.append(serializer.data)
            
        return Response(data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)