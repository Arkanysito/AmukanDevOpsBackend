# apps/booking/views.py

from rest_framework import viewsets, permissions
from .models import Booking
from .serializers import BookingSerializer
from django.contrib.contenttypes.models import ContentType
from rest_framework.response import Response

class BookingViewSet(viewsets.ModelViewSet):
    """
    API endpoint para las reservas (Bookings).
    Maneja la creación (POST) y listado (GET).
    """
    
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra las reservas para que un usuario solo vea las suyas.
        """
        user = self.request.user
        
        # Pre-cargamos el 'user' y el 'content_type' para optimizar
        queryset = Booking.objects.select_related('user', 'content_type')

        if user.is_staff:
            queryset = queryset.all()
        else:
            queryset = queryset.filter(user=user) 
        
        return queryset.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        """
        Sobrescribimos 'list' para optimizar la GenericForeignKey.
        Esto evita un error 500 por N+1 queries.
        """
        queryset = self.get_queryset()
        
        # 1. Obtenemos los bookings
        bookings = list(queryset)
        
        # 2. Creamos un mapa para buscar los items (Events, Activities, etc.)
        items_map = {} # { 'event': [uuid1, uuid2], 'activityservice': [uuid3] }
        for booking in bookings:
            model_name = booking.content_type.model
            if model_name not in items_map:
                items_map[model_name] = []
            items_map[model_name].append(booking.object_id)
        
        # 3. Hacemos una consulta por cada TIPO de item
        fetched_items = {} # { uuid1: event_obj, uuid3: activity_obj }
        for model_name, object_ids in items_map.items():
            try:
                model_class = ContentType.objects.get(model=model_name).model_class()
                pk_name = model_class._meta.pk.name
                # Buscamos todos los items de este tipo de una sola vez
                items = model_class.objects.filter(**{f"{pk_name}__in": object_ids})
                for item in items:
                    fetched_items[item.pk] = item
            except ContentType.DoesNotExist:
                print(f"Advertencia: No se encontró ContentType para el modelo '{model_name}'")

        # 4. "Cosemos" los datos de vuelta en los bookings
        for booking in bookings:
            related_item = fetched_items.get(booking.object_id)
            # Añadimos el objeto pre-cargado al 'booking'
            # para que el serializer.data lo use
            booking.reservable_item = related_item

        # Serializamos los bookings (que ahora tienen 'reservable_item' cacheado)
        serializer = self.get_serializer(bookings, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """
        Asigna automáticamente el usuario actual al crear una nueva reserva.
        """
        serializer.save(user=self.request.user)