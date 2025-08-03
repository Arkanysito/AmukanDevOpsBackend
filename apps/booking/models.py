from django.db import models
import uuid
from apps.experiences.models import Event, Service
from apps.users.models import User
from apps.core.constants import Currency, ReservationStatus

class Reservation(models.Model):
    reservation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    service_id = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    event_id = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
