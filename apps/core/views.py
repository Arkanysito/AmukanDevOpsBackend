from rest_framework.views import APIView
from rest_framework.response import Response
from .constants import Gender, Nationality, Language
from django.http import JsonResponse, HttpResponseForbidden
from apps.core.metabase_embed import build_signed_embed_url_for_dashboard
from django.views.decorators.cache import never_cache
from django.utils.cache import add_never_cache_headers
from apps.organizations.models import OrganizationUser
from apps.organizations.permissions import OrganizationChecker
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

class ChoicesView(APIView):
    def get(self, request):
        return Response({
            "gender": [{"value": choice.value, "label": choice.label} for choice in Gender],
            "nationality": [{"value": choice.value, "label": choice.label} for choice in Nationality],
            "language": [{"value": choice.value, "label": choice.label} for choice in Language],
        })

DASHBOARD_ID = 2  # tu dashboard en Metabase



@api_view(["GET"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated, OrganizationChecker])
@never_cache
def get_org_dashboard_embed_url(request):
    # Ya no hace falta chequear is_authenticated: lo hizo IsAuthenticated
    link = (
        OrganizationUser.objects
        .select_related("organization_id")
        .filter(user_id=request.user)
        .first()
    )
    if not link:
        return Response({"detail": "Usuario sin organización"}, status=403)

    org = link.organization_id

    # Usa EXACTAMENTE los slugs de Metabase
    locked_params = {
        "filtro_1": "BOOK",
        "filtro_2": org.name,   # cuando migres a UUID, cambia al param correspondiente
    }

    signed_url = build_signed_embed_url_for_dashboard(
        dashboard_id=DASHBOARD_ID,
        locked_parameters=locked_params,
        token_ttl_seconds=120,   # opcional: TTL corto para reducir exposición
    )

    resp = Response({"url": signed_url})
    add_never_cache_headers(resp)
    return resp