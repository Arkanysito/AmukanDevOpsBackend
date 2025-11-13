# /app/apps/destinationSearch/views/accommodations.py
from rest_framework.views import APIView
from apps.experiences.models import AccommodationService
from apps.location.models import Place
from apps.destinationSearch.serializers import PlaceAccommodationSerializer 
from .common import standard_response
from apps.core.constants import PlaceType # Importado

class AccommodationListView(APIView):
    def get(self, request):
        params = request.query_params
        budget = params.get("budget")
        travelers = params.get("travelers")
        
        ordering = params.get("ordering")

        accommodation_types = [
            PlaceType.HOTEL.value,
            PlaceType.HOSTEL.value, 
            PlaceType.GUEST_HOUSE.value,
            PlaceType.APARTMENT.value,
            PlaceType.RESORT.value,
            PlaceType.BED_BREAKFAST.value,
            PlaceType.MOTEL.value,
            PlaceType.CAMPSITE.value,
        ]
        
        querys = Place.objects.filter(type__in=accommodation_types).select_related(
            'organization_id', 
            'zone_id', 
            'cover_image'
        )
        
        if budget:
            querys = querys.filter(average_price__lte=budget)
        
        # if travelers:
        #    querys = querys.filter(capacity__gte=travelers)

        if ordering == "price_asc":
            querys = querys.order_by("average_price")
        elif ordering == "price_desc":
            querys = querys.order_by("-average_price")
        else:
            # Orden por defecto si no es por precio
            querys = querys.order_by("-rating") 

        return standard_response(querys, PlaceAccommodationSerializer, "alojamientos")