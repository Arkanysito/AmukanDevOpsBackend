from rest_framework.views import APIView
from rest_framework.response import Response
from apps.destinationSearch.serializers import EventSerializer

class EventListView(APIView):
    def get(self, request):
        
        return Response(EventSerializer(many=True).data, status=200)