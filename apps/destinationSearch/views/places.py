from rest_framework.views import APIView
from apps.location.models import Place
from apps.destinationSearch.serializers import PlaceSerializer
from .common import standard_response

class PlaceListView(APIView):
    def get(self, request):
        params = request.query_params
        place_type = params.get("type")

        querys = Place.objects.all()
        if place_type:
            querys = querys.filter(type=place_type)

        return standard_response(querys, PlaceSerializer, "places")