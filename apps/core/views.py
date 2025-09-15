from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from .constants import Gender, Nationality
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET
from apps.core.metabase_embed import build_signed_embed_url_for_dashboard
from apps.organizations.models import OrganizationUser

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
        })

DASHBOARD_ID = 2  # tu dashboard en Metabase



@require_GET
def get_org_dashboard_embed_url(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Auth requerida")

    link = (
        OrganizationUser.objects
        .select_related("organization_id")
        .filter(user_id=request.user)
        .first()
    )
    if not link:
        return HttpResponseForbidden("Usuario sin organización")

    org = link.organization_id

    # ⇨ Usa EXACTAMENTE los slugs que muestra Metabase: filtro_1 y filtro_2
    locked_params = {
        "filtro_1": "BOOK",         # como en tu dashboard
        "filtro_2": org.name,       # hoy filtras por nombre; luego puedes migrar a UUID
    }

    signed_url = build_signed_embed_url_for_dashboard(
        dashboard_id=DASHBOARD_ID,
        locked_parameters=locked_params,
        token_ttl_seconds=900,
    )
    return JsonResponse({"url": signed_url})