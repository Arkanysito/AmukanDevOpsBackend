from rest_framework.views import APIView
from apps.experiences.models import AccommodationService
from apps.location.models import Place
from apps.destinationSearch.serializers import PlaceAccommodationSerializer 
from .common import standard_response

class AccommodationListView(APIView):
    def get(self, request):
        params = request.query_params
        budget = params.get("budget")
        travelers = params.get("travelers")

        # CÓDIGO ORIGINAL DE AccommodationService:
        # querys = AccommodationService.objects.all()
        # if budget:
        #     querys = querys.filter(price__lte=budget)
        # if travelers:
        #     querys = querys.filter(room_capacity__gte=travelers)

        # Usar Place en lugar de AccommodationService
        from apps.core.constants import PlaceType
        
        # Definir tipos de alojamiento en Place
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
        
        # Filtrar lugares que sean de tipo alojamiento
        querys = Place.objects.filter(type__in=accommodation_types)
        
        # Aplicar filtros si existen
        if budget:
            # Usar average_price en lugar de price
            querys = querys.filter(average_price__lte=budget)
        
        # NOTA: Place no tiene room_capacity, pero el serializer proporciona valores por defecto
        # if travelers:
        #    querys = querys.filter(room_capacity__gte=travelers)

        # NUEVO SERIALIZER
        return standard_response(querys, PlaceAccommodationSerializer, "alojamientos")