# apps/booking/admin.py

from django.contrib import admin
from .models import Booking
from django.utils.html import format_html

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """
    Panel de Administración para el modelo Booking.
    (Versión corregida para que coincida con tus models.py)
    """
    
    list_display = (
        'booking_id', 
        'user', 
        'reservable_item_display',
        'start_date',
        'state',
        'total_price',
        'created_at'
    )
    
    list_filter = ('state', 'created_at', 'organization')
    search_fields = ('booking_id', 'user__username')
    
    readonly_fields = (
        'booking_id', 
        'created_at',
        'content_type', 
        'object_id', 
        'reservable_item_display'
    )
    
    fieldsets = (
        ('Información de la Reserva', {
            'fields': ('booking_id', 'user', 'state', 'created_at')
        }),
        ('Item Reservado (Lectura)', {
            'fields': ('reservable_item_display', 'content_type', 'object_id')
        }),
        ('Detalles y Fechas', {
            'fields': ('start_date', 'end_date', 'cantidad_personas', 'total_price', 'price_currency') 
        }),
        ('Relaciones (Opcional)', {
            'fields': ('organization',),
        })
    )
    
    def get_queryset(self, request):
        # Optimizamos la consulta para pre-cargar el usuario
        return super().get_queryset(request).select_related('user')

    @admin.display(description='Item Reservado')
    def reservable_item_display(self, obj):
        """
        Muestra el nombre del item reservado (usando la GenericForeignKey).
        """
        if obj.reservable_item:
            return str(obj.reservable_item)
        return "---"