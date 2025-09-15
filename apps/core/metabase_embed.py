import time
import jwt
from django.conf import settings

def build_signed_embed_url_for_dashboard(
    dashboard_id: int,
    locked_parameters: dict,
    token_ttl_seconds: int = 900,
) -> str:
    payload = {
        "resource": {"dashboard": dashboard_id},
        "params": locked_parameters,
        "exp": round(time.time()) + token_ttl_seconds,
    }
    token = jwt.encode(payload, settings.METABASE_EMBEDDING_SECRET, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return f"{settings.METABASE_PUBLIC_BASE_URL}/embed/dashboard/{token}#bordered=false&titled=false"
