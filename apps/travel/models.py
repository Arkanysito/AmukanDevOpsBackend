import uuid
from django.db import models
from apps.booking.models import Reservation
from apps.core.constants import Currency, UserRole
from apps.users.models import Interest, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class Itinerary(models.Model):
    itinerary_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_shared = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} - {self.created_at}"


class ItineraryItem(models.Model):
    item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    itinerary_id = models.ForeignKey(Itinerary, on_delete=models.CASCADE)
    reservation_id = models.ForeignKey(Reservation, on_delete=models.CASCADE, null=True, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    reservable = GenericForeignKey('content_type', 'object_id')
    scheduled_date = models.DateTimeField()
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2)
    estimated_cost_currency = models.CharField(max_length=3, choices=Currency.choices)

    def __str__(self):
        return f"{self.itinerary_id.name} - {self.content_type.model} - {self.scheduled_date}"


class ItineraryCollaborator(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    itinerary_id = models.ForeignKey(Itinerary, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices
    )

    class Meta:
        unique_together = ('user_id', 'itinerary_id')

    def __str__(self):
        return f"{self.user_id.username} - {self.itinerary_id.name} - {self.role}"
