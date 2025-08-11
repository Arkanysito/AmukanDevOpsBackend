from rest_framework.views import APIView
from apps.experiences.models import AccommodationService
from apps.destinationSearch.serializers import AccommodationServiceSerializer
from .common import standard_response

class AccommodationListView(APIView):
    def get(self, request):
        params = request.query_params
        budget = params.get("budget")
        travelers = params.get("travelers")

        querys = AccommodationService.objects.all()
        if budget:
            querys = querys.filter(price__lte=budget)
        if travelers:
            querys = querys.filter(room_capacity__gte=travelers)

        return standard_response(querys, AccommodationServiceSerializer, "alojamientos")
