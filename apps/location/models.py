from django.contrib.gis.db import models
import uuid
from apps.organizations.models import Organization
from apps.core.constants import ZoneLevel, PlaceType

class Zone(models.Model):
    zone_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_zone_id = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    level = models.CharField(
        max_length=20,
        choices=ZoneLevel.choices
    )
    coordinates = models.PolygonField(geography=True)

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

    def __str__(self):
        if self.zone_id:
            return f"{self.name}, Zone: {self.zone_id.name}"
        return f"{self.name}, Zone: Unknown"

    
