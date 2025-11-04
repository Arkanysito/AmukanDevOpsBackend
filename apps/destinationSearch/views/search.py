import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.destinationSearch.serializers import *
from .filters import *
from .common import standard_response
from apps.tracking.models import Interaction
from apps.core.constants import InteractionAction

class SearchAllView(APIView):
    def post(self, request):
        budget = request.data.get("budget")
        travelers = request.data.get("travelers")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")

        # Ejecutar filtros
        events = filter_events(budget, start_date, end_date)
        accommodations = filter_accommodations(budget, travelers)
        activities = filter_activities(budget)

        # Guardar interacción
        Interaction.objects.create(
            user_id=request.user if request.user.is_authenticated else None,
            session_id=request.session.session_key or 'anonymous',
            action=InteractionAction.SEARCH,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            metadata={
                "budget": budget,
                "travelers": travelers,
                "start_date": start_date,
                "end_date": end_date,
                "filters_used": True
            }
        )

        return Response({
            "events": standard_response(events, EventSerializer, "eventos").data,
            "accommodations": standard_response(accommodations, AccommodationServiceSerializer, "alojamientos").data,
            "activities": standard_response(activities, ActivityServiceSerializer, "actividades").data
        })

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip