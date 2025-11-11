from django.db import models
import uuid
from apps.organizations.models import Organization
from apps.location.models import Place
from apps.core.constants import AccommodationType, ActivityType, Currency, TransportType
from django.contrib.postgres.fields import ArrayField
from apps.recommendation.ml_model import encode_texts

class AbstractService(models.Model):
    service_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    place_id = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True)
    organization_id = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    price_currency = models.CharField(max_length=3, choices=Currency.choices)
    details = models.JSONField(blank=True, null=True)
    policies = models.JSONField(blank=True, null=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    capacity = models.PositiveIntegerField(default=1)
    embedding = ArrayField(models.FloatField(), size=384, null=True, blank=True) 
    cover_image = models.ForeignKey(
        "core.Image",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_cover_image",
        db_index=True,
      )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name} - {self.organization_id.name} - {self.price}"

    def _generate_embedding_text(self):
        """
        Construye el texto que se usará para generar el embedding.
        """
        text_parts = [self.name, self.description]
        
        # Añadir tipo de servicio para más contexto
        if hasattr(self, 'accommodation_type'):
            text_parts.append(self.get_accommodation_type_display())
        elif hasattr(self, 'activity_type'):
            text_parts.append(self.get_activity_type_display())

        return " ".join(filter(None, text_parts))

    def save(self, *args, **kwargs):
        """
        Sobrescribe save() para generar el embedding automáticamente.
        """
        # Evita recursión si solo estamos guardando el embedding
        if 'update_fields' in kwargs and list(kwargs['update_fields']) == ['embedding']:
            super().save(*args, **kwargs)
            return

        # Genera el texto y el embedding
        text_to_embed = self._generate_embedding_text()
        if text_to_embed:
            vector = encode_texts(text_to_embed) 
            self.embedding = vector[0].tolist()
        else:
            self.embedding = None
        
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            kwargs['update_fields'] = list(set(list(kwargs['update_fields'])) | {'embedding'})

        super().save(*args, **kwargs)


class AccommodationService(AbstractService):
    accommodation_type = models.CharField(max_length=15, choices=AccommodationType.choices)
    amenities = models.JSONField(blank=True, null=True)
    beds = models.IntegerField()
    check_in_time = models.TimeField()
    check_out_time = models.TimeField()
    parking = models.BooleanField(default=False)
    
class ActivityService(AbstractService):
    activity_type = models.CharField(max_length=15, choices=ActivityType.choices)
    duration_minutes = models.IntegerField()
    guide_included = models.BooleanField(default=False)
    details = models.JSONField(blank=True, null=True)

class Event(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.ForeignKey(Organization, on_delete=models.CASCADE)
    place_id = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    price_currency = models.CharField(max_length=3, choices=Currency.choices)
    details = models.JSONField(blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    embedding = ArrayField(models.FloatField(), size=384, null=True, blank=True)
    capacity = models.PositiveIntegerField(default=50) # número total de entradas/tickets para el evento.
    cover_image = models.ForeignKey(
        "core.Image",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="event_cover_image",
        db_index=True,
    )

    def __str__(self):
        return f"{self.name} - {self.organization_id.name} - {self.price}"
    
    def _generate_embedding_text(self):
        """
        Construye el texto para el embedding del evento.
        """
        text_parts = [self.name, self.description]
        return " ".join(filter(None, text_parts))

    def save(self, *args, **kwargs):
        """
        Sobrescribe save() para generar el embedding automáticamente.
        """
        # Evita recursión
        if 'update_fields' in kwargs and list(kwargs['update_fields']) == ['embedding']:
            super().save(*args, **kwargs)
            return

        text_to_embed = self._generate_embedding_text()
        if text_to_embed:
            vector = encode_texts(text_to_embed)
            self.embedding = vector[0].tolist()
        else:
            self.embedding = None
        
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            kwargs['update_fields'] = list(set(list(kwargs['update_fields'])) | {'embedding'})

        super().save(*args, **kwargs)