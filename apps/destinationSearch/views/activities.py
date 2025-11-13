from rest_framework.views import APIView
from apps.location.models import Place
from apps.destinationSearch.serializers import PlaceSerializer
from apps.core.constants import PlaceType
from .common import standard_response

class ActivityListView(APIView):
    def get(self, request):
        params = request.query_params
        budget = params.get("budget")
        place_type = params.get("type")

        ordering = params.get("ordering")

        interesting_categories = [
            PlaceType.PARK, PlaceType.MUSEUM, PlaceType.BEACH, PlaceType.VIEWPOINT,
            PlaceType.LIBRARY, PlaceType.CINEMA, PlaceType.THEATRE, PlaceType.STADIUM,
            PlaceType.SPORTS_CENTRE, PlaceType.MARKETPLACE, PlaceType.SHOP, PlaceType.MALL,
            PlaceType.ZOO, PlaceType.AQUARIUM, PlaceType.NIGHTCLUB, PlaceType.ATTRACTION,
            PlaceType.ARTWORK, PlaceType.GALLERY, PlaceType.THEME_PARK, PlaceType.GARDEN,
            PlaceType.SWIMMING_POOL, PlaceType.GOLF_COURSE, PlaceType.FITNESS_CENTRE,
            PlaceType.PLAYGROUND, PlaceType.MONUMENT, PlaceType.MEMORIAL, PlaceType.CASTLE,
            PlaceType.RUINS, PlaceType.ARCHAEOLOGICAL_SITE, PlaceType.BOOKS,
            PlaceType.CONCERT_HALL, PlaceType.BOTANICAL_GARDEN, PlaceType.HOT_SPRING,
            PlaceType.SKI_RESORT, PlaceType.ADVENTURE_PARK, PlaceType.ART_GALLERY,
            PlaceType.HISTORIC_SITE, PlaceType.SHOPPING_MALL, PlaceType.MARKET,
        ]
        
        interesting_types = [pt.value for pt in interesting_categories]
        
        querys = Place.objects.filter(type__in=interesting_types).select_related(
            'organization_id', 
            'zone_id', 
            'cover_image'
        )
        
        if budget:
            querys = querys.filter(average_price__lte=budget)
        
        if place_type:
            querys = querys.filter(type=place_type)

        if ordering == "price_asc":
            querys = querys.order_by("average_price")
        elif ordering == "price_desc":
            querys = querys.order_by("-average_price")
        else:
            # Orden por defecto si no es por precio
            querys = querys.order_by("-rating")

        return standard_response(querys, PlaceSerializer, "actividades")