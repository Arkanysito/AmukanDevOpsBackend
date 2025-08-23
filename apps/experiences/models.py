from django.db import models
import uuid
from apps.organizations.models import Organization
from apps.location.models import Place
from apps.core.constants import AccommodationType, ActivityType, Currency, TransportType

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

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name} - {self.organization_id.name} - {self.price}"

class TransportService(AbstractService):
    transport_type = models.CharField(max_length=10, choices=TransportType.choices)
    schedule = models.JSONField(blank=True, null=True)
    capacity = models.IntegerField(null=True, blank=True)


class AccommodationService(AbstractService):
    accommodation_type = models.CharField(max_length=15, choices=AccommodationType.choices)
    amenities = models.JSONField(blank=True, null=True)
    beds = models.IntegerField()
    room_capacity = models.IntegerField()
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

    def __str__(self):
        return f"{self.name} - {self.organization_id.name} - {self.price}"
    
    

