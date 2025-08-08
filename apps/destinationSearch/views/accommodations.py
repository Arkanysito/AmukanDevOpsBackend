from rest_framework.views import APIView
from rest_framework.response import Response
from apps.experiences.models import AccommodationService
from ..serializers import AccommodationServiceSerializer

class AccommodationListView(APIView):
    def get(self, request):
        destination = request.GET.get('destination')
        travelers = request.GET.get('travelers')
        budget = request.GET.get('budget')

        queryset = AccommodationService.objects.all()

        if destination:
            queryset = queryset.filter(place_id__name__icontains=destination)
        if travelers:
            queryset = queryset.filter(room_capacity__gte=int(travelers))
        if budget:
            queryset = queryset.filter(price__lte=float(budget))

        serializer = AccommodationServiceSerializer(queryset, many=True)
        return Response(serializer.data)
