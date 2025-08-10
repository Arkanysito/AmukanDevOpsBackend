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

    # FK polimórfica opcional
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    action = models.CharField(max_length=20, choices=InteractionAction.choices)
    interaction_date = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)

    # Campo flexible para parámetros dinámicos (JSONB en PostgreSQL)
    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['action']),
            models.Index(fields=['interaction_date']),
        ]

    def __str__(self):
        return f"{self.session_id} - {self.action}"


class InteractionStats(models.Model):
    interaction_stats_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Fecha/hora de agregación
    date = models.DateField()

    # Tipo y referencia opcional al objeto
    object_type = models.CharField(max_length=50)  # Ej: "Event", "Place", "Search"
    object_id = models.UUIDField(null=True, blank=True)

    # Acción agregada
    action = models.CharField(max_length=20, choices=InteractionAction.choices)

    # Métricas agregadas
    total_interactions = models.PositiveIntegerField(default=0)
    unique_users = models.PositiveIntegerField(default=0)
    avg_duration_sec = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    avg_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    top_filter = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['object_type']),
            models.Index(fields=['action']),
        ]
        verbose_name_plural = "Interaction Stats"

    def __str__(self):
        return f"{self.date} - {self.object_type} - {self.action}"