from rest_framework.views import APIView
from apps.experiences.models import ActivityService
from apps.destinationSearch.serializers import ActivityServiceSerializer
from .common import standard_response

class ActivityListView(APIView):
    def get(self, request):
        params = request.query_params
        budget = params.get("budget")

        querys = ActivityService.objects.all()
        if budget:
            querys = querys.filter(price__lte=budget)

        return standard_response(querys, ActivityServiceSerializer, "actividades")