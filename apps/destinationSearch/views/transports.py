from rest_framework.views import APIView
from apps.experiences.models import TransportService
from apps.destinationSearch.serializers import TransportServiceSerializer
from .common import standard_response

class TransportListView(APIView):
    def get(self, request):
        params = request.query_params
        budget = params.get("budget")
        travelers = params.get("travelers")

        querys = TransportService.objects.all()
        if budget:
            querys = querys.filter(price__lte=budget)
        if travelers:
            querys = querys.filter(capacity__gte=travelers)

        return standard_response(querys, TransportServiceSerializer, "transportes")