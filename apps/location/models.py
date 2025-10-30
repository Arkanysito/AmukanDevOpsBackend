from django.contrib.gis.db import models
import uuid
from apps.organizations.models import Organization
from apps.core.constants import ZoneLevel, PlaceType
from django.contrib.postgres.fields import ArrayField
from apps.recommendation.ml_model import encode_texts

class Zone(models.Model):
    zone_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_zone_id = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    level = models.CharField(
        max_length=20,
        choices=ZoneLevel.choices
    )
    coordinates = models.MultiPolygonField(geography=True)

    def __str__(self):
        return f"{self.name} - {self.level}"


class Place(models.Model):
    place_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True)
    zone_id = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    type = models.CharField(
        max_length=20,
        choices=PlaceType.choices,
    )
    coordinates = models.PointField(geography=True)
    accessibility_features = models.JSONField(blank=True, null=True)
    average_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    schedule = models.JSONField(blank=True, null=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0)
    embedding = ArrayField(models.FloatField(), size=384, null=True, blank=True)
    cover_image = models.ForeignKey(
        "core.Image",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="place_cover_image",
        db_index=True,
    )


    def __str__(self):
        if self.zone_id:
            return f"{self.name}, Zone: {self.zone_id.name}"
        return f"{self.name}, Zone: Unknown"
    
    def _generate_embedding_text(self):
        """
        Construye el texto que se usará para generar el embedding del Place.
        Usamos los campos más descriptivos.
        """
        text_parts = [
            self.name,
            self.description,
            self.get_type_display(),
            self.address
        ]
        # Une solo los strings que no son None o vacíos
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
            # Llama a tu función de ML
            vector = encode_texts(text_to_embed) 
            self.embedding = vector[0].tolist()
        else:
            self.embedding = None
        
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            # Usamos set() para evitar duplicados y luego lo volvemos lista
            kwargs['update_fields'] = list(set(list(kwargs['update_fields'])) | {'embedding'})

        super().save(*args, **kwargs)