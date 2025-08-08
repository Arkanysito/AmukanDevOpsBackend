from rest_framework.views import APIView
from rest_framework.response import Response
from apps.destinationSearch.serializers import (
    EventSerializer,
    AccommodationServiceSerializer,
    ActivityServiceSerializer
)
from .filters import *

class SearchAllView(APIView):
    def post(self, request):
        budget = request.data.get("budget")
        travelers = request.data.get("travelers")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")

        events = filter_events(budget, start_date, end_date)
        accommodations = filter_accommodations(budget, travelers)
        activities = filter_activities(budget)

        return Response({
            "events": EventSerializer(events, many=True).data,
            "accommodations": AccommodationServiceSerializer(accommodations, many=True).data,
            "activities": ActivityServiceSerializer(activities, many=True).data
        })