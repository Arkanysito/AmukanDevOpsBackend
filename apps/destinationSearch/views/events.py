from rest_framework.views import APIView
from apps.experiences.models import Event
from apps.destinationSearch.serializers import EventSerializer
from .filters import filter_events
from .common import standard_response
from django.utils import timezone

class EventListView(APIView):
    def get(self, request):
        params = request.query_params
        ordering = params.get("ordering")
        
        querys = filter_events(
            budget=params.get("budget"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        )
        
        # Si el usuario NO especificó un rango de fechas,
        # mostramos solo los eventos que no han terminado.
        if not params.get("start_date") and not params.get("end_date"):
            now = timezone.now()
            querys = querys.filter(end_date__gte=now)
        
        if ordering == "price_asc":
            querys = querys.order_by("price")
        elif ordering == "price_desc":
            querys = querys.order_by("-price")
        else:
            # Orden por defecto si no es por precio
            querys = querys.order_by("-rating") 
        querys = querys[:20]
        return standard_response(querys, EventSerializer, "eventos")