from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from .services import recommend_places

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommend_places_view(request):
    try:
        recommendations = recommend_places(request.user, top_k=10)
        data = []
        for place, score in recommendations:
            data.append({
                "id": str(place.place_id),
                "name": place.name,
                "type": place.type,
                "description": place.description,
                "rating": place.rating,
                "score": float(score)
            })
        return Response(data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


