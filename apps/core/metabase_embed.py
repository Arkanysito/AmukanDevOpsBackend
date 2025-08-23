import time, jwt
from django.conf import settings

'''
def signed_embed(resource: dict, params: dict, ttl_secs: int = 600) -> str:
    """
    resource: {"dashboard": <id>}  o  {"question": <id>}
    params:   {"organization_id": "<uuid/string>", ...}
    """
    payload = {"resource": resource, "params": params, "exp": round(time.time()) + ttl_secs}
    token = jwt.encode(payload, settings.MB_EMBEDDING_APP_SECRET, algorithm="HS256")
    kind = next(iter(resource))  # "dashboard" | "question"
    return f"{settings.METABASE_SITE_URL}/embed/{kind}/{token}#bordered=false&titled=false"

'''