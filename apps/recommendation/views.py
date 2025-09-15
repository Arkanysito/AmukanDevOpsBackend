from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .services import recommend_places
from .serializers import PlaceRecoSerializer
from django.http import JsonResponse

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommend_places_view(request):
    try:
        places = recommend_places(request.user, top_k=10)
        data = [{"id": str(p.place_id), "name": p.name, } for p in places]
        return Response(data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


