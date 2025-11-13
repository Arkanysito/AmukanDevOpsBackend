# /app/apps/destinationSearch/views/places.py
from rest_framework.views import APIView
from apps.location.models import Place
from apps.destinationSearch.serializers import PlaceSerializer
from .common import standard_response
from apps.core.constants import PlaceType

class PlaceListView(APIView):
    def get(self, request):
        params = request.query_params
        place_type = params.get("type")
        
        ordering = params.get("ordering")

        querys = Place.objects.select_related(
            'organization_id', 
            'zone_id', 
            'cover_image'
        )
        
        if place_type == "restaurant":
            # Si se piden "restaurant", incluir toda la categoría gastronomía
            gastronomy_types = [
                PlaceType.RESTAURANT.value,
                PlaceType.CAFE.value,
                PlaceType.BAR.value,
                PlaceType.PUB.value,
            ]
            querys = querys.filter(type__in=gastronomy_types)
        elif place_type:
            querys = querys.filter(type=place_type)
            
        if ordering == "price_asc":
            querys = querys.order_by("average_price")
        elif ordering == "price_desc":
            querys = querys.order_by("-average_price")
        else:
            querys = querys.order_by("-rating")

        return standard_response(querys, PlaceSerializer, "places")