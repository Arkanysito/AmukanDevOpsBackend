import uuid
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class Tag(models.Model):
    tag_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}"

class ObjectTag(models.Model):
    object_tag_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag_id = models.ForeignKey(Tag, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    reservable = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return f"{self.tag_id.name} - {self.content_type.model}"

