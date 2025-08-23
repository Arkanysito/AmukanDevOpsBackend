from django.shortcuts import render
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET
from .metabase_embed import signed_embed_url

@require_GET
def metabase_embed_url(request):
    # obtén org_id del usuario autenticado o por querystring 'org'
    user = request.user
    org_id = getattr(user, "organization_id", None) or request.GET.get("org")
    kind = request.GET.get("type", "dashboard")  # "dashboard" | "question"
    try:
        mb_id = int(request.GET.get("id", "0"))
    except ValueError:
        return HttpResponseForbidden("id inválido")
    if not org_id or mb_id <= 0:
        return HttpResponseForbidden("Faltan parámetros")

    url = signed_embed_url(resource={kind: mb_id}, params={"organization_id": str(org_id)})
    return JsonResponse({"url": url})

