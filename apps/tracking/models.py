from django.db import models
import uuid
from apps.users.models import CustomUser
from apps.core.constants import InteractionAction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class Interaction(models.Model):
    interaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    session_id = models.CharField(max_length=255)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    reservable = GenericForeignKey('content_type', 'object_id')

    action = models.CharField(max_length=20, choices=InteractionAction.choices)
    interaction_date = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.session_id} - {self.action}"

