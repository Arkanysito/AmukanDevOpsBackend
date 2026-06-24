import logging
from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework.views import APIView
from rest_framework.response import Response
from .constants import Gender, Nationality, Language, ActivityType, AccommodationType, PlaceType, Currency, OrganizationCategory
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.cache import never_cache
from django.utils.cache import add_never_cache_headers
from rest_framework.decorators import api_view, authentication_classes, permission_classes, parser_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from apps.organizations.models import OrganizationUser
from apps.core.metabase_embed import build_signed_embed_url_for_dashboard
import jwt
import os, uuid
from django.utils.timezone import now
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Image
from .s3_utils import s3_client,build_public_url


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

# --- Configuración de Dashboards ---
PUBLIC_DASHBOARD_ID = 3  # <-- ID del Dashboard para org públicas
PRIVATE_DASHBOARD_ID = 2 # <-- ID del Dashboard para cualquier otra org"

METABASE_PARAM_NAME = "org_id" # Hay que crear un filtro con este mismo nombre



@api_view(["GET"])
@authentication_classes([JWTAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@never_cache
def get_org_dashboard_embed_url(request):
    try:
        # 1. Obtenemos el OrganizationUser y la Organización asociada
        # Usamos select_related para obtener el objeto Organization en una sola consulta
        org_user = OrganizationUser.objects.select_related('organization_id').get(user_id=request.user) #
        org = org_user.organization_id #

    except OrganizationUser.DoesNotExist:
        return Response({"detail": "Usuario sin organización"}, status=403)

    # 2. Obtenemos los datos de la organización
    org_category = org.category
    org_uuid_str = str(org.organization_id)

    # 3. Lógica para decidir qué dashboard y qué parámetros usar
    if org_category == OrganizationCategory.GOVERNMENT: 
        # Es GOBIERNO: usa el dashboard público, sin parámetros
        dashboard_id_to_use = PUBLIC_DASHBOARD_ID
        locked_params = {
            METABASE_PARAM_NAME: org_uuid_str
        } 
    
    else:
        dashboard_id_to_use = PRIVATE_DASHBOARD_ID
        locked_params = {
            # Bloquea el dashboard para que *solo* muestre datos de esta org
            METABASE_PARAM_NAME: org_uuid_str
        }

    signed_url = build_signed_embed_url_for_dashboard(
        dashboard_id=dashboard_id_to_use,
        locked_parameters=locked_params,
    )

    if request.GET.get("debug") == "1":
        token = signed_url.split("/embed/dashboard/")[1].split("#")[0]
        payload = jwt.decode(token, options={"verify_signature": False})
        return Response({
            "url": signed_url,
            "token": token,
            "payload": payload,                   
            "context": {
                "user_id": getattr(request.user, "id", None),
                "organization_uuid": org_uuid_str,
                "organization_category": org_category,
                "dashboard_id_sent": dashboard_id_to_use,
                "params_sent": locked_params,
                "metabase_base": settings.METABASE_PUBLIC_BASE_URL,
            }
        })
    return Response({"url": signed_url})

MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", "5242880"))
ALLOWED_CT = set(os.getenv("UPLOAD_ALLOWED_CONTENT_TYPES", "image/jpeg,image/png,image/webp").split(","))
BUCKET = os.getenv("S3_BUCKET_NAME", "amukan")

def _build_key(org_id, filename):
    t = now()
    return f"images/{org_id or 'public'}/{t.year:04d}/{t.month:02d}/{uuid.uuid4()}/{filename}"

@api_view(["POST"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_image(request):
    """
    Subida directa: el front envía multipart/form-data con 'file' (+ opcional 'organization_id').
    El backend sube a MinIO y guarda solo metadatos en la tabla Image.
    """
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "Falta 'file'."}, status=400)

    organization_id = request.data.get("organization_id")
    key = _build_key(organization_id, f.name)
    ct = getattr(f, "content_type", None) or "application/octet-stream"

    s3 = s3_client()
    # Si tu bucket es público, puedes dejar ACL. Si es privado, elimina ExtraArgs y usa presigned URLs (no es el caso aquí).
    s3.upload_fileobj(
        f, BUCKET, key,
        ExtraArgs={"ContentType": ct, "ACL": "public-read"}
    )

    img = Image.objects.create(
        object_key=key,
        content_type=ct,
        filename=f.name,
        organization_id=organization_id,
        created_by=request.user,
        status=Image.Status.STORED,
        size_bytes=f.size,
    )

    return Response({
        "image_id": str(img.id),
        "object_key": key,
        "bucket": BUCKET,
        "content_type": ct,
        "size": f.size,
        "public_url": build_public_url(BUCKET, key),
    }, status=201)