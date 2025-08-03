from django.db import models
import uuid
from apps.organizations.models import Organization
from apps.location.models import Place
from apps.core.constants import Currency

class ServiceType(models.Model):
    service_type_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

class Service(models.Model):
    service_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_type_id = models.ForeignKey(ServiceType, on_delete=models.CASCADE)
    place_id = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True)
    organization_id = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    price_currency = models.CharField(max_length=3, choices=Currency.choices)
    details = models.JSONField(blank=True, null=True)
    policies = models.JSONField(blank=True, null=True)

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
    
    

