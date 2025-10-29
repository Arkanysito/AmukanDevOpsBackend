from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, authentication_classes, permission_classes, parser_classes
from .constants import Gender, Nationality, Language, ActivityType, AccommodationType, PlaceType, Currency
from django.http import JsonResponse, HttpResponseForbidden
from apps.core.metabase_embed import build_signed_embed_url_for_dashboard
from django.views.decorators.cache import never_cache
from django.utils.cache import add_never_cache_headers
from apps.organizations.models import OrganizationUser
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from apps.organizations.models import OrganizationUser
from apps.core.metabase_embed import build_signed_embed_url_for_dashboard
from .constants import Gender, Nationality, Language
import jwt
import os, uuid
from django.utils.timezone import now
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Image
from .s3_utils import s3_client



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

MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", "5242880"))
ALLOWED_CT = set(os.getenv("UPLOAD_ALLOWED_CONTENT_TYPES", "image/jpeg,image/png,image/webp").split(","))
BUCKET = os.getenv("S3_BUCKET_NAME", "amukan")

def _build_key(org_id, filename):
    t = now()
    return f"images/{org_id or 'public'}/{t.year:04d}/{t.month:02d}/{uuid.uuid4()}/{filename}"

@api_view(["POST"])
@authentication_classes([SessionAuthentication, JWTAuthentication])  # ya importados en tu archivo
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_image(request):
    """
    Subida directa: el front envía multipart/form-data con 'file' (+ opcional 'organization_id').
    Django hace stream a MinIO y solo guardamos metadatos + object_key en la tabla Image.
    """
    f = request.FILES.get("file")
    organization_id = request.data.get("organization_id")

    if not f:
        return Response({"detail": "archivo 'file' requerido"}, status=400)

    ct = f.content_type or "application/octet-stream"
    if ct not in ALLOWED_CT:
        return Response({"detail": "content_type no permitido"}, status=400)

    if f.size <= 0 or f.size > MAX_BYTES:
        return Response({"detail": f"tamaño inválido (max {MAX_BYTES} bytes)"}, status=400)

    key = _build_key(organization_id, f.name)

    s3_client().put_object(
        Bucket=BUCKET,
        Key=key,
        Body=f,              # Django File stream
        ContentType=ct,
        ACL="private",
    )

    img = Image.objects.create(
        object_key=key,
        bucket=BUCKET,
        storage="s3",
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
    }, status=201)