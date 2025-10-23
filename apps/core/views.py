from rest_framework.views import APIView
from rest_framework.response import Response
from .constants import Gender, Nationality, Language, ActivityType, AccommodationType, PlaceType, Currency
from django.http import JsonResponse, HttpResponseForbidden
from apps.core.metabase_embed import build_signed_embed_url_for_dashboard
from django.views.decorators.cache import never_cache
from django.utils.cache import add_never_cache_headers
from apps.organizations.models import OrganizationUser
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings 
import jwt

class ChoicesView(APIView):
    def get(self, request):
        return Response({
            "gender": [{"value": choice.value, "label": choice.label} for choice in Gender],
            "nationality": [{"value": choice.value, "label": choice.label} for choice in Nationality],
            "language": [{"value": choice.value, "label": choice.label} for choice in Language],
            "activityType": [{"value": choice.value, "label": choice.label} for choice in ActivityType],
            "accommodationType": [{"value": choice.value, "label": choice.label} for choice in AccommodationType],
            "placeType": [{"value": choice.value, "label": choice.label} for choice in PlaceType],
            "currency": [{"value": choice.value, "label": choice.label} for choice in Currency],
        })

DASHBOARD_ID = 2  # tu dashboard en Metabase



@api_view(["GET"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated])
@never_cache
def get_org_dashboard_embed_url(request):
    org_uuid = OrganizationUser.objects.filter(user_id=request.user)\
        .values_list("organization_id__organization_id", flat=True).first()

    if not org_uuid:
        return Response({"detail": "Usuario sin organización"}, status=403)

    
    signed_url = build_signed_embed_url_for_dashboard(
        dashboard_id=DASHBOARD_ID,
        locked_parameters={"organization_id": str(org_uuid)},
        
    )

    if request.GET.get("debug") == "1":
        token = signed_url.split("/embed/dashboard/")[1].split("#")[0]
        #Para inspección
        payload = jwt.decode(token, options={"verify_signature": False})
        return Response({
            "url": signed_url,
            "token": token,
            "payload": payload,                   
            "context": {
                "user_id": getattr(request.user, "id", None),
                "organization_uuid": str(org_uuid),
                "dashboard_id": DASHBOARD_ID,
                "metabase_base": settings.METABASE_PUBLIC_BASE_URL,
            }
        })
    return Response({"url": signed_url})