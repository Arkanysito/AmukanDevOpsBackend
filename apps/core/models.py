import uuid
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from apps.core.constants import ImagePosition

class Image(models.Model):
    image_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.TextField(null=False, blank=False)
    position = models.CharField(max_length=50, choices=ImagePosition.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    reservable = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return f"{self.url}"


