from rest_framework.views import APIView
from apps.experiences.models import Event
from apps.destinationSearch.serializers import EventSerializer
from .filters import filter_events
from .common import standard_response

class EventListView(APIView):
    def get(self, request):
        params = request.query_params
        querys = filter_events(
            budget=params.get("budget"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        )
        return standard_response(querys, EventSerializer, "eventos")