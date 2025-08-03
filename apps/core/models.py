import uuid
from django.db import models

from apps.core.constants import ImagePosition, ObjectType

class Image(models.Model):
    image_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.TextField(null=False, blank=False)
    position = models.CharField(max_length=50, choices=ImagePosition.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    object_id = models.UUIDField()
    object_type = models.CharField(max_length=50, choices=ObjectType.choices)


