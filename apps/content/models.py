import uuid
from django.db import models
from apps.core.constants import ObjectType

class Tag(models.Model):
    tag_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

class ObjectTag(models.Model):
    object_tag_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag_id = models.ForeignKey(Tag, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    object_type = models.CharField(max_length=50, choices=ObjectType.choices)

