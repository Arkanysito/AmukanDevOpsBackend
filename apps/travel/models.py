import uuid
from django.db import models
from apps.booking.models import Reservation
from apps.core.constants import Currency, ObjectType, UserRole
from apps.users.models import Interest, User

class Itinerary(models.Model):
    itinerary_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_shared = models.BooleanField(default=False)


class ItineraryItem(models.Model):
    item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    itinerary_id = models.ForeignKey(Itinerary, on_delete=models.CASCADE)
    reservation_id = models.ForeignKey(Reservation, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.UUIDField()
    object_type = models.CharField(max_length=50, choices=ObjectType.choices)
    scheduled_date = models.DateTimeField()
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2)
    estimated_cost_currency = models.CharField(max_length=3, choices=Currency.choices)


class ItineraryCollaborator(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    interest_id = models.ForeignKey(Interest, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices
    )

    class Meta:
        unique_together = ('user_id', 'interest_id')
