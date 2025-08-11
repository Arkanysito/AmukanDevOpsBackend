from rest_framework.views import APIView
from rest_framework.response import Response
from apps.destinationSearch.serializers import *
from .filters import *
from .common import standard_response

class SearchAllView(APIView):
    def post(self, request):
        budget = request.data.get("budget")
        travelers = request.data.get("travelers")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")

        events = filter_events(budget, start_date, end_date)
        accommodations = filter_accommodations(budget, travelers)
        transports = filter_transports(budget,travelers)
        activities = filter_activities(budget)

        return Response({
            "events": standard_response(events, EventSerializer, "eventos").data,
            "accommodations": standard_response(accommodations, AccommodationServiceSerializer, "alojamientos").data,
            "transports": standard_response(transports, TransportServiceSerializer, "transportes").data,
            "activities": standard_response(activities, ActivityServiceSerializer, "actividades").data
        })