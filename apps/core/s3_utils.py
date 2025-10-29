import os, boto3
def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://minio:9000"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minio"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minio12345"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
    )

from django.conf import settings

def build_public_url(bucket: str, key: str) -> str:
    """
    Devuelve la URL pública completa del objeto en MinIO.
    Usa el endpoint público definido en settings.py.
    """
    base = getattr(settings, "S3_ENDPOINT_PUBLIC", "") or getattr(settings, "S3_ENDPOINT_URL", "")
    base = base.rstrip("/")
    return f"{base}/{bucket}/{key.lstrip('/')}"