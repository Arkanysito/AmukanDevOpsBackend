from rest_framework.views import APIView
from rest_framework.response import Response
from apps.experiences.models import ActivityService
from apps.destinationSearch.serializers import ActivityServiceSerializer


class ActivityListView(APIView):
    def get(self, request):
        destination = request.GET.get('destination')
        budget = request.GET.get('budget')

        queryset = ActivityService.objects.all()

        if destination:
            queryset = queryset.filter(place_id__name__icontains=destination)
        if budget:
            queryset = queryset.filter(price__lte=float(budget))

        serializer = ActivityServiceSerializer(queryset, many=True)
        return Response(serializer.data)
