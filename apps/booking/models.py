import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from apps.organizations.models import Organization

User = get_user_model()

class Booking(models.Model):
    """
    Una reserva (Booking) que puede vincularse a cualquier
    servicio (Alojamiento, Actividad) o Evento.
    """
    class BookingStatus(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        CONFIRMADA = 'confirmada', 'Confirmada'
        CANCELADA = 'cancelada', 'Cancelada'
        RECHAZADA = 'rechazada', 'Rechazada'

    booking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    user = models.ForeignKey(User, related_name='bookings', on_delete=models.SET_NULL, null=True) 
    organization = models.ForeignKey(Organization, related_name='bookings', on_delete=models.CASCADE)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField() 
    reservable_item = GenericForeignKey('content_type', 'object_id')

    
    # --- Detalles de la Reserva ---
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    cantidad_personas = models.PositiveIntegerField(default=1)
    
    state = models.CharField(
        max_length=10, 
        choices=BookingStatus.choices, 
        default=BookingStatus.PENDIENTE
    )
    
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    price_currency = models.CharField(max_length=3) # Ej. "CLP"

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking {self.booking_id} para {self.user.username if self.user else 'Usuario desconocido'}"

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gt=models.F('start_date')),
                name='booking_end_date_after_start_date'
            )
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]