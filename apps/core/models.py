import uuid
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from apps.core.constants import ImagePosition

import uuid
from django.db import models
from django.conf import settings

class Image(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        STORED  = "stored",  "Stored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # S3/MinIO
    object_key   = models.CharField(max_length=512, unique=True)
    bucket       = models.CharField(max_length=128, default="amukan")
    storage      = models.CharField(max_length=32, default="s3")

    # Metadatos verificados
    content_type = models.CharField(max_length=64, blank=True, default="")
    size_bytes   = models.PositiveIntegerField(default=0)
    width        = models.PositiveIntegerField(null=True, blank=True)
    height       = models.PositiveIntegerField(null=True, blank=True)
    etag         = models.CharField(max_length=64, blank=True, default="")
    checksum_md5 = models.CharField(max_length=32, blank=True, default="")

    # Multi-tenant / auditoría
    organization_id = models.UUIDField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="images"
    )

    status     = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    filename   = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_image"
        indexes = [
            models.Index(fields=["organization_id", "created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.id} ({self.status}) -> {self.object_key}"


