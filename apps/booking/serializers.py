# apps/booking/serializers.py

from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from .models import Booking
from django.contrib.auth import get_user_model
from apps.experiences.models import Event, AccommodationService, ActivityService

User = get_user_model()

class BookingSerializer(serializers.ModelSerializer):
    """
    Serializer para LEER y CREAR Bookings.
    Maneja la lógica de validación de capacidad y solapamiento.
    """
    
    # --- Campos para LEER (GET) ---
    # (Usados por la vista 'MisItinerarios')
    usuario_username = serializers.ReadOnlyField(source='user.username')
    service_details = serializers.SerializerMethodField()
    estado_display = serializers.CharField(source='get_state_display', read_only=True)

    # --- Campos para CREAR (POST) ---
    # (Usados por la vista 'Checkout.jsx')
    item_type = serializers.CharField(write_only=True, required=False)
    item_id = serializers.UUIDField(write_only=True, required=False)
    itinerary_item_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Booking
        fields = [
            # Campos de Modelo (usados por GET y POST)
            'booking_id', 'organization', 'start_date', 'end_date', 
            'cantidad_personas', 'state', 'total_price', 'price_currency',
            'created_at', 'user',

            # Campos calculados (solo GET)
            'usuario_username', 'service_details', 'estado_display', 
            
            # Campos de ayuda (solo POST)
            'item_type', 'item_id', 'itinerary_item_id'
        ]
        read_only_fields = [
            'booking_id', 'organization', 'total_price', 
            'price_currency', 'created_at', 'service_details', 
            'estado_display', 'usuario_username', 'user' # El usuario se setea en 'create'
        ]
        
        # 'start_date' y 'end_date' son requeridos por el modelo,
        # pero los validamos en la lógica 'validate'
        extra_kwargs = {
            'start_date': {'required': False},
            'end_date': {'required': False},
        }

    def get_service_details(self, obj):
        """
        Devuelve el nombre y tipo del item reservado (para vistas GET).
        """
        if not obj.reservable_item:
            return None
        item = obj.reservable_item
        return {
            'name': getattr(item, 'name', 'Servicio Desconocido'),
            'type': obj.content_type.model,
        }

    def validate(self, data):
        """
        Validación central para crear la reserva (vía POST).
        """
        # Esta validación SÓLO se aplica al crear (POST)
        if self.context['request'].method != 'POST':
            return data # No validar nada al leer (GET) o actualizar (PUT/PATCH)

        item_type = data.get('item_type')
        item_id = data.get('item_id')
        cantidad_personas = data.get('cantidad_personas')
        fecha_inicio = data.get('start_date')
        fecha_fin = data.get('end_date')

        # Validamos que los campos obligatorios para POST estén
        if not all([item_type, item_id, cantidad_personas, fecha_inicio, fecha_fin]):
            raise serializers.ValidationError(
                "Para crear una reserva se requieren: 'item_type', 'item_id', "
                "'cantidad_personas', 'start_date' y 'end_date'."
            )

        # 1. Encontrar el item reservable
        model_class = None
        try:
            if item_type == 'activity':
                model_class = ActivityService
            elif item_type == 'accommodation':
                model_class = AccommodationService
            elif item_type == 'event':
                model_class = Event
            else:
                raise serializers.ValidationError(f"Tipo de item no válido: '{item_type}'.")
            
            # Buscamos el item por su PK (event_id, service_id, etc.)
            pk_name = model_class._meta.pk.name 
            reservable_item = model_class.objects.get(**{pk_name: item_id})

        except model_class.DoesNotExist:
            raise serializers.ValidationError(f"El item con ID {item_id} no existe.")
        except Exception as e:
            # Captura genérica para depurar
            raise serializers.ValidationError(f"Error interno al buscar item: {str(e)}")

        # 2. Validar capacidad (Asumiendo que tus modelos tienen 'capacity')
        if not hasattr(reservable_item, 'capacity'):
            raise serializers.ValidationError(f"El item '{reservable_item.name}' no tiene 'capacity' y no se puede reservar.")
        
        capacidad_maxima = reservable_item.capacity
        content_type = ContentType.objects.get_for_model(reservable_item)

        # 3. Buscar solapamientos
        reservas_solapadas = Booking.objects.filter(
            content_type=content_type,
            object_id=reservable_item.pk,
            state='confirmada',
            start_date__lt=fecha_fin,
            end_date__gt=fecha_inicio
        )
        
        total_personas_reservadas = reservas_solapadas.aggregate(
            total=Sum('cantidad_personas')
        )['total'] or 0

        if (total_personas_reservadas + cantidad_personas) > capacidad_maxima:
            disponible = capacidad_maxima - total_personas_reservadas
            raise serializers.ValidationError(
                f"No hay capacidad. Solo quedan {disponible} cupos."
            )
            
        # 4. Inyectar datos calculados
        # El nombre del campo en Event/Service es 'organization_id' (ForeignKey)
        # El nombre del campo en Booking es 'organization' (ForeignKey)
        data['organization'] = reservable_item.organization_id # Asigna el objeto Organization
        data['total_price'] = reservable_item.price * cantidad_personas
        data['price_currency'] = reservable_item.price_currency
        
        # Guardamos el objeto para usarlo en 'create'
        data['reservable_item_obj'] = reservable_item 
        
        return data

    def create(self, validated_data):
        """
        Crea el objeto Booking en la base de datos.
        """
        # Extraemos los datos que no son parte del modelo Booking
        reservable_item = validated_data.pop('reservable_item_obj')
        itinerary_item_id = validated_data.pop('itinerary_item_id', None)
        validated_data.pop('item_type', None) # Quitar helpers
        validated_data.pop('item_id', None)   # Quitar helpers
        
        # Asignamos el usuario desde el contexto de la vista
        validated_data['user'] = self.context['request'].user
        
        # Asignamos el item genérico
        validated_data['reservable_item'] = reservable_item

        # Creamos la reserva
        booking = Booking.objects.create(**validated_data)

        # --- Opcional: Vinculamos al Itinerario (si se proveyó) ---
        if itinerary_item_id:
            try:
                # Importamos ItineraryItem aquí para evitar importación circular
                from apps.travel.models import ItineraryItem
                item = ItineraryItem.objects.get(item_id=itinerary_item_id)
                item.booking = booking # Vinculamos la reserva recién creada
                item.save(update_fields=['booking'])
            except ItineraryItem.DoesNotExist:
                print(f"Booking {booking.booking_id} creado, pero no se encontró ItineraryItem {itinerary_item_id}")
        
        return booking