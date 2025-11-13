# apps/travel/views.py

from django.utils import timezone
from datetime import datetime, time, timedelta
import pytz
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
#from apps.travel.itineray_generator import generate_optimized_itineraries
from apps.travel.services import generate_optimized_itineraries
from apps.users.models import CustomUser
from apps.core.constants import InteractionAction
from apps.tracking.models import Interaction
import json
from .serializers import ItinerarySerializer, ItineraryWithItemsSerializer
from django.db import transaction
from apps.travel.models import Itinerary, ItineraryItem, ItineraryCollaborator
from django.contrib.contenttypes.models import ContentType
import uuid
import logging
from apps.core.constants import UserRole
from apps.experiences.models import Event, AccommodationService, ActivityService
from apps.location.models import Place
from rest_framework import generics
from django.db.models import Prefetch

logger = logging.getLogger(__name__)

class ItineraryPreviewView(APIView):
    def post(self, request):
        data = request.data
        destino = data.get("destino")
        desde = data.get("desde")
        hasta = data.get("hasta")
        presupuesto = data.get("presupuesto", 0)
        cantidad_personas = data.get("cantidad_personas", 1)
        # 'preferences' ya no se usa, solo 'experiencias'
        experiencias = data.get("experiencias", [])

        # Validaciones
        if not all([destino, desde, hasta]):
            return Response({"error": "Faltan campos obligatorios"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Convertir strings a datetime
            desde_dt = datetime.fromisoformat(desde.replace('Z', '+00:00'))
            hasta_dt = datetime.fromisoformat(hasta.replace('Z', '+00:00'))

            # Hacer las fechas timezone-aware
            desde = timezone.make_aware(desde_dt)
            hasta = timezone.make_aware(hasta_dt)

            # Timezone de Chile
            chile_tz = pytz.timezone('Chile/Continental')
            hoy = timezone.now().astimezone(chile_tz).date()

            desde_chile = desde.astimezone(chile_tz)
            hasta_chile = hasta.astimezone(chile_tz)

            if desde_chile.date() == hoy:
                desde = timezone.now().astimezone(chile_tz)

            if hasta_chile.date() == hoy:
                hasta = chile_tz.localize(datetime.combine(hoy, time(23, 59, 59)))

            elif hasta_chile.date() != hoy:
                hasta = chile_tz.localize(datetime.combine(
                    hasta_chile.date() + timedelta(days=1), 
                    time(3, 0)
                ))

            presupuesto = float(presupuesto)
            cantidad_personas = int(cantidad_personas)
            
        except (ValueError, TypeError) as e:
            return Response({"error": f"Parámetros inválidos: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Generar itinerarios optimizados
        itinerarios = generate_optimized_itineraries(
            request=request,
            destination=destino,
            start_date=desde,
            end_date=hasta,
            budget=presupuesto,
            travelers=cantidad_personas,
            experiencias=experiencias,
        )

        # GUARDAR LA BÚSQUEDA EN LA BASE DE DATOS
        self._save_search_interaction(
            request, destino, desde, hasta, presupuesto, cantidad_personas,
            itinerarios, experiencias
        )

        if not itinerarios.get('itineraries'):
            return Response({
                "message": "No se pudo generar un itinerario con los parámetros dados",
                "suggestion": "Intente con un destino diferente o verifique la disponibilidad de servicios"
            }, status=status.HTTP_204_NO_CONTENT)

        # Formatear respuesta para el frontend
        response_data = self._format_itineraries_for_frontend(
            itinerarios, destino, desde, hasta, cantidad_personas
        )

        return Response(response_data, status=status.HTTP_200_OK)

    def _save_search_interaction(self, request, destino, desde, hasta, presupuesto, cantidad_personas, itinerarios, experiencias=None):
        """Guarda la búsqueda en la base de datos como una interacción (incluye experiencias)"""
        try:
            # Obtener información del usuario y sesión
            user = request.user if request.user.is_authenticated else None
            session_id = self._get_session_id(request)

            # Preparar metadata de la búsqueda
            metadata = {
                'search_parameters': {
                    'destino': destino,
                    'desde': desde.isoformat() if hasattr(desde, 'isoformat') else str(desde),
                    'hasta': hasta.isoformat() if hasattr(hasta, 'isoformat') else str(hasta),
                    'presupuesto': presupuesto,
                    'cantidad_personas': cantidad_personas,
                    'experiencias': experiencias or [],
                },
                'search_results': {
                    'itineraries_count': len(itinerarios.get('itineraries', [])) if isinstance(itinerarios, dict) and 'itineraries' in itinerarios else len(itinerarios) if isinstance(itinerarios, list) else 0,
                    'total_cost_range': self._get_cost_range(itinerarios),
                    'strategies_available': self._get_available_strategies(itinerarios)
                },
                'request_info': {
                    'ip_address': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'timestamp': timezone.now().isoformat()
                }
            }

            # Crear la interacción
            interaction = Interaction.objects.create(
                user_id=user,
                session_id=session_id,
                action=InteractionAction.SEARCH,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                metadata=metadata
            )

            return interaction

        except Exception as e:
            # Log del error pero no interrumpir el flujo principal
            logger.error(f"Error al guardar interacción de búsqueda: {str(e)}")
            return None

    def _get_session_id(self, request):
        """Obtiene el session_id de la request"""
        if hasattr(request, 'session') and request.session.session_key:
            return request.session.session_key
        elif request.user.is_authenticated:
            return f"user_{request.user.id}"
        else:
            # Generar un session_id único para usuarios anónimos
            import uuid
            return f"anon_{uuid.uuid4().hex[:16]}"

    def _get_client_ip(self, request):
        """Obtiene la IP real del cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _get_cost_range(self, itinerarios):
        """Obtiene el rango de costos de los itinerarios generados"""
        if not itinerarios:
            return {'min': 0, 'max': 0}
        
        try:
            if isinstance(itinerarios, dict) and 'itineraries' in itinerarios:
                costs = [itinerario.get('total_cost', 0) for itinerario in itinerarios['itineraries']]
            elif isinstance(itinerarios, list):
                costs = [itinerario.get('total_cost', 0) for itinerario in itinerarios]
            else:
                return {'min': 0, 'max': 0}

            valid_costs = [cost for cost in costs if cost is not None and cost > 0] # Check for None
            if valid_costs:
                return {
                    'min': min(valid_costs),
                    'max': max(valid_costs)
                }
        except (KeyError, TypeError, ValueError):
            pass
        
        return {'min': 0, 'max': 0}

    def _get_available_strategies(self, itinerarios):
        """Obtiene las estrategias disponibles en los resultados"""
        if not itinerarios:
            return []

        try:
            if isinstance(itinerarios, dict) and 'itineraries' in itinerarios:
                strategies = [itinerario.get('strategy', 'unknown') for itinerario in itinerarios['itineraries']]
            elif isinstance(itinerarios, list):
                strategies = [itinerario.get('strategy', 'unknown') for itinerario in itinerarios]
            else:
                return []

            return list(set(strategies))  # Remover duplicados
        except (KeyError, TypeError):
            return []
    
    def _format_itineraries_for_frontend(self, itinerarios, destino, desde, hasta, cantidad_personas):
        """Formatea los itinerarios agregando número de día a cada servicio"""
        formatted_itineraries = []
        dias_totales = max(1, (hasta - desde).days + 1)

        # Asegurarse de que estamos accediendo a la lista correcta
        if isinstance(itinerarios, dict) and 'itineraries' in itinerarios:
            itinerarios_list = itinerarios['itineraries']
        elif isinstance(itinerarios, list):
             itinerarios_list = itinerarios
        else:
             itinerarios_list = [] # Asegurar que sea una lista

        for idx, itinerario in enumerate(itinerarios_list):
            # Volver a la estructura original sin "lugares"
            servicios = {
                "hospedaje": [],
                "transporte": [],
                "comida": [],
                "actividades": [],
                "eventos": []
                # "lugares": [] -> Eliminado
            }

            # Verificar que itinerario tenga la estructura esperada
            if isinstance(itinerario, dict) and 'items' in itinerario:
                for item in itinerario["items"]:
                    servicio_formateado = self._format_service_item(item)

                    # Agregar número de día al servicio
                    dia_numero = self._obtener_numero_dia(item, desde)
                    servicio_formateado["dia"] = dia_numero

                    # Mapear tipos al formato que espera el frontend
                    tipo_frontend = self._map_service_type_to_frontend(item['type'])
                    if tipo_frontend and tipo_frontend in servicios:
                        servicios[tipo_frontend].append(servicio_formateado)
                    elif tipo_frontend:
                        logger.warning(f"Tipo frontend '{tipo_frontend}' (mapeado desde '{item['type']}') no encontrado en diccionario 'servicios'")

                # Calcular duración
                if dias_totales == 1:
                    duracion = "1 día"
                else:
                    duracion = f"{dias_totales} días / {max(0, dias_totales - 1)} noches" # Asegurar noches >= 0

                formatted_itineraries.append({
                    "id": idx + 1,
                    "titulo": f"Itinerario {idx+1} para {destino} ({itinerario.get('strategy', 'standard')})",
                    "duracion": duracion,
                    "cantidad_personas": cantidad_personas,
                    "presupuesto": float(itinerario.get("total_cost", 0)), # Usar .get con default
                    "utilizacion_presupuesto": float(itinerario.get("budget_utilization", 0)),
                    "servicios": servicios
                })

        return formatted_itineraries

    def _obtener_numero_dia(self, item, start_date):
        """Obtiene el número de día basado en la fecha del item"""
        item_date = item.get('date')
        if not item_date:
            return 1  # Default al primer día

        # Asegurarse que start_date sea timezone-aware
        if start_date and not timezone.is_aware(start_date):
             start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        # Asegurarse que item_date sea timezone-aware
        if isinstance(item_date, str):
            item_date = datetime.fromisoformat(item_date.replace('Z', '+00:00'))
        elif isinstance(item_date, datetime) and not timezone.is_aware(item_date):
             item_date = timezone.make_aware(item_date, timezone.get_current_timezone())

        if not isinstance(item_date, datetime) or not start_date:
             logger.warning(f"No se pudo calcular el día para el item: {item}. Usando día 1.")
             return 1

        # Calcular diferencia de días (usando .date() para ignorar horas)
        try:
             diferencia = (item_date.date() - start_date.date()).days
             return max(1, diferencia + 1)
        except Exception as e:
             logger.error(f"Error calculando diferencia de días: {e}. Item date: {item_date}, Start date: {start_date}")
             return 1


    def _map_service_type_to_frontend(self, backend_type):
        """Mapea los tipos del backend a los que espera el frontend"""
        # Mapear 'activity' y 'place_activity' a 'actividades'
        type_mapping = {
            'accommodation': 'hospedaje',
            'dining': 'comida',
            'activity': 'actividades',
            'place_activity': 'actividades', # Mapeado a actividades
            'transport': 'transporte',
            'event': 'eventos',
            # 'place_activity': 'lugares'
        }
        return type_mapping.get(backend_type)

    def _format_service_item(self, item):
        """Formatea un item de servicio para la respuesta"""
        service = item.get('service')
        item_cost = item.get('cost', 0.0) # Default a 0.0

        if service is None:
            # Servicio genérico (fallback)
            formatted_service = {
                "id": "", # ID vacío para servicios genéricos
                "nombre": item.get('description', 'Servicio'),
                "descripcion": item.get('description', 'Servicio incluido en el itinerario'),
                "rating": 0.0,
                "fecha": item['date'].isoformat() if 'date' in item and item['date'] else None,
                "costo": float(item_cost), # Usar item_cost
                "coordenadas": self._get_coordinates(service),
                "duracion": item.get('duration_hours'),
                "tipo_comida": item.get('meal_type'),
                "backend_type": item.get('type')
            }
        else:
            # Servicio de la base de datos
            current_backend_type = item.get('type') # El tipo del generador

            # Determinar el ID primario Y el tipo_backend_real según la instancia
            if isinstance(service, AccommodationService):
                service_id = getattr(service, 'service_id', None)
                backend_type_real = 'accommodation'
            elif isinstance(service, ActivityService):
                service_id = getattr(service, 'service_id', None)
                backend_type_real = 'activity'
            elif isinstance(service, Place):
                service_id = getattr(service, 'place_id', None)
                # Mapear 'accommodation' o 'activity' (del generador) a 'place_activity'
                if current_backend_type in ['dining', 'place_activity']:
                    backend_type_real = current_backend_type
                else:
                    # Si el generador dijo 'accommodation' pero es un Place,
                    # lo tratamos como 'place_activity'
                    backend_type_real = 'place_activity'
            elif isinstance(service, Event):
                service_id = getattr(service, 'event_id', None)
                backend_type_real = 'event'
            else:
                # Fallback
                service_id = getattr(service, 'service_id', None) or \
                             getattr(service, 'place_id', None) or \
                             getattr(service, 'event_id', None) or None
                backend_type_real = current_backend_type


            formatted_service = {
                "id": str(service_id) if service_id else '',
                "nombre": getattr(service, 'name', 'Servicio'),
                "descripcion": getattr(service, 'description', ''),
                "rating": float(getattr(service, 'rating', 0.0)),
                "fecha": item['date'].isoformat() if 'date' in item and item['date'] else None,
                "costo": float(item_cost), # Usar item_cost
                "coordenadas": self._get_coordinates(service),
                "duracion": item.get('duration_hours'),
                "tipo_comida": item.get('meal_type'),
                "backend_type": backend_type_real
            }

        # Para eventos, agregar información específica
        if item.get('type') == 'event' and hasattr(service, 'start_date'):
            formatted_service.update({
                "fecha_inicio": service.start_date.isoformat() if service.start_date else None,
                "fecha_fin": service.end_date.isoformat() if service.end_date else None,
                "es_evento": True
            })

        # Asegurarse de que las coordenadas estén en formato WKT si existen
        coords = formatted_service["coordenadas"]
        if coords and isinstance(coords, dict):
            try:
                # Intentar convertir a WKT, manejar posible error si faltan keys
                lng = coords.get('lng', 'N/A')
                lat = coords.get('lat', 'N/A')
                if lng != 'N/A' and lat != 'N/A':
                     formatted_service["coordenadas"] = f"POINT({lng} {lat})"
                else:
                     logger.warning(f"Coordenadas incompletas para {formatted_service.get('nombre')}: {coords}")
                     formatted_service["coordenadas"] = None # O un valor por defecto
            except Exception as e:
                logger.error(f"Error convirtiendo coordenadas a WKT para {formatted_service.get('nombre')}: {e}")
                formatted_service["coordenadas"] = None # Fallback a None
        elif isinstance(coords, str) and not coords.startswith("POINT"):
             # Si es string pero no WKT, intentar limpiarlo o poner None
             logger.warning(f"Formato de coordenadas inesperado (string no WKT) para {formatted_service.get('nombre')}: {coords}")
             formatted_service["coordenadas"] = None


        return formatted_service

    def _get_coordinates(self, obj):
        """Obtiene las coordenadas de un objeto en formato consistente"""
        if obj is None:
            return None

        # Intentar diferentes formas de obtener coordenadas
        coordinates = None

        # 1. Coordenadas directas del objeto (Place)
        if hasattr(obj, 'coordinates') and obj.coordinates:
            coordinates = obj.coordinates
        # 2. Coordenadas a través de place_id (ActivityService, Event)
        elif hasattr(obj, 'place_id') and hasattr(obj.place_id, 'coordinates') and obj.place_id.coordinates:
            coordinates = obj.place_id.coordinates

        # Convertir a formato consistente {lat: Y, lng: X}
        if coordinates:
            if hasattr(coordinates, 'x') and hasattr(coordinates, 'y'):
                # Es un PointField de GeoDjango
                return {"lat": float(coordinates.y), "lng": float(coordinates.x)}
            elif hasattr(coordinates, 'wkt'):
                 # Es un string WKT, intentar parsearlo
                 try:
                      import re
                      match = re.match(r'POINT\(\s*([-\d.]+)\s+([-\d.]+)\s*\)', coordinates.wkt)
                      if match:
                           lng, lat = match.groups()
                           return {"lat": float(lat), "lng": float(lng)}
                 except Exception as e:
                      logger.error(f"Error parseando WKT: {coordinates.wkt} - {e}")
            elif isinstance(coordinates, dict) and 'lat' in coordinates and 'lng' in coordinates:
                 # Ya está en el formato deseado
                 return coordinates

        logger.warning(f"No se pudieron obtener coordenadas válidas para el objeto: {obj}")
        return None

class SaveItineraryView(APIView):
    def post(self, request):
        logger.info("✅ SaveItineraryView llamado")

        try:
            data = request.data
            user = request.user

            if not user.is_authenticated:
                return Response(
                    {"error": "Debe estar autenticado para guardar itinerarios"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            required_fields = ['name', 'itinerario_data']
            for field in required_fields:
                if field not in data:
                    return Response(
                        {"error": f"Campo requerido faltante: {field}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            with transaction.atomic():
                # Crear el itinerario
                itinerary = Itinerary.objects.create(
                    name=data['name'],
                    is_shared=data.get('is_shared', False)
                )
                logger.info(f"📝 Itinerario creado: {itinerary.itinerary_id}")

                # Agregar al usuario como colaborador
                ItineraryCollaborator.objects.create(
                    user_id=user,
                    itinerary_id=itinerary,
                    role=UserRole.OWNER
                )

                # Procesar items del itinerario
                items_creados = self._create_itinerary_items(itinerary, data['itinerario_data'])
                
                # CREAR RESERVAS AUTOMÁTICAS PARA EVENTOS
                reservas_creadas = self._create_automatic_bookings(user, items_creados, data['itinerario_data'])
                logger.info(f"📅 Reservas automáticas creadas: {len(reservas_creadas)}")

                # GUARDAR INTERACCIÓN DE GUARDADO DE ITINERARIO
                self._save_itinerary_save_interaction(request, itinerary, data['itinerario_data'], items_creados)

                # ACTUALIZAR PERFIL DEL USUARIO BASADO EN EL ITINERARIO
                self._update_user_profile_from_itinerary(user, data['itinerario_data'])

                return Response({
                    "message": "Itinerario guardado exitosamente",
                    "itinerary_id": str(itinerary.itinerary_id),
                    "name": itinerary.name,
                    "items_count": len(items_creados),
                    "bookings_created": len(reservas_creadas),
                    "items_by_type": {k: len(v) for k, v in data['itinerario_data'].get('servicios', {}).items()}
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"❌ Error al guardar itinerario: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Error al guardar itinerario: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _create_automatic_bookings(self, user, itinerary_items, itinerario_data):
        """
        Crea o actualiza reservas automáticas para eventos en LOTE (BULK).
        """
        from apps.booking.models import Booking
        
        reservas_afectadas = []
        items_para_actualizar_booking = [] # Para actualizar ItineraryItem.booking
        
        # 1. Filtrar solo los items que son 'event'
        event_content_type = None
        try:
            event_content_type = ContentType.objects.get(model='event', app_label='experiences')
        except ContentType.DoesNotExist:
            logger.error("❌ ContentType para 'event' no existe. No se crearán reservas.")
            return []

        event_items = [item for item in itinerary_items if item.content_type_id == event_content_type.id]
        if not event_items:
            logger.info("ℹ️ No hay eventos en el itinerario. No se crearán reservas.")
            return []

        # 2. Obtener todos los IDs de los eventos y los objetos Event en sí
        event_object_ids = [item.object_id for item in event_items]
        eventos_map = {
            e.event_id: e for e in Event.objects.filter(
                event_id__in=event_object_ids
            ).select_related('organization_id') # Optimización N+1
        }

        # 3. Obtener todas las reservas EXISTENTES para estos eventos y este usuario
        existing_bookings_qs = Booking.objects.filter(
            user=user,
            content_type=event_content_type,
            object_id__in=event_object_ids
        )
        existing_bookings_map = {b.object_id: b for b in existing_bookings_qs}
        
        cantidad_personas_paquete = itinerario_data.get('cantidad_personas', 1)
        
        bookings_to_create = []
        bookings_to_update = []

        # 4. Separar las que hay que crear de las que hay que actualizar
        for item in event_items:
            evento = eventos_map.get(item.object_id)
            
            if not evento:
                logger.warning(f"⚠️ Evento (ID: {item.object_id}) no encontrado en la BD. Saltando reserva.")
                continue
            if not evento.organization_id:
                logger.warning(f"❌ Evento {evento.name} no tiene organización. Saltando reserva.")
                continue
            
            event_price = (evento.price or 0)
            
            if item.object_id in existing_bookings_map:
                # --- Preparar para ACTUALIZAR (UPDATE) ---
                booking = existing_bookings_map[item.object_id]
                booking.cantidad_personas += cantidad_personas_paquete
                booking.total_price = event_price * booking.cantidad_personas
                bookings_to_update.append(booking)
                item.booking = booking # Asignar la instancia
                items_para_actualizar_booking.append(item)
            else:
                # --- Preparar para CREAR (CREATE) ---
                booking = Booking(
                    user=user,
                    organization=evento.organization_id,
                    content_type=item.content_type,
                    object_id=item.object_id,
                    cantidad_personas=cantidad_personas_paquete,
                    start_date=evento.start_date,
                    end_date=evento.end_date,
                    total_price=event_price * cantidad_personas_paquete,
                    price_currency=getattr(evento, 'price_currency', 'CLP')
                )
                bookings_to_create.append(booking)
                # item.booking se asignará después de que se cree el booking (en el paso 6)

        # 5. Ejecutar operaciones en LOTE (BULK)
        try:
            if bookings_to_update:
                Booking.objects.bulk_update(bookings_to_update, ['cantidad_personas', 'total_price'])
                reservas_afectadas.extend(bookings_to_update)
                logger.info(f"✅ Reservas actualizadas (bulk): {len(bookings_to_update)}")

            if bookings_to_create:
                created_bookings = Booking.objects.bulk_create(bookings_to_create)
                reservas_afectadas.extend(created_bookings)
                logger.info(f"✅ Reservas creadas (bulk): {len(created_bookings)}")
                
                # 6. Mapear items nuevos a sus bookings recién creados
                created_bookings_map = {b.object_id: b for b in created_bookings}
                for item in event_items:
                    if not item.booking: # Si aún no tiene un booking asignado (es nuevo)
                        booking = created_bookings_map.get(item.object_id)
                        if booking:
                            item.booking = booking
                            items_para_actualizar_booking.append(item)

            # 7. Actualizar TODOS los ItineraryItem con su FK de booking en LOTE
            if items_para_actualizar_booking:
                ItineraryItem.objects.bulk_update(items_para_actualizar_booking, ['booking'])
                logger.info(f"✅ Items de itinerario actualizados con FK de booking (bulk): {len(items_para_actualizar_booking)}")

        except Exception as e:
            logger.error(f"❌ Error en operaciones bulk de reserva: {str(e)}", exc_info=True)

        return reservas_afectadas

    def _get_session_id(self, request):
        """Obtiene el session_id de la request"""
        if hasattr(request, 'session') and request.session.session_key:
            return request.session.session_key
        elif request.user.is_authenticated:
            return f"user_{request.user.id}"
        else:
            # Generar un session_id único para usuarios anónimos
            import uuid
            return f"anon_{uuid.uuid4().hex[:16]}"

    def _get_client_ip(self, request):
        """Obtiene la IP real del cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _save_itinerary_save_interaction(self, request, itinerary, itinerario_data, items_creados):
        """Guarda la interacción de guardado de itinerario incluyendo experiencias"""
        try:
            user = request.user if request.user.is_authenticated else None
            session_id = self._get_session_id(request)

            # Extraer información relevante para el perfilado
            servicios = itinerario_data.get('servicios', {})
            # 'preferences' ya no se usa
            experiencias = itinerario_data.get('experiencias', [])

            metadata = {
                'itinerary_info': {
                    'itinerary_id': str(itinerary.itinerary_id),
                    'name': itinerary.name,
                    'total_items': len(items_creados),
                    'items_by_type': {k: len(v) for k, v in servicios.items()}
                },
                # 'user_preferences': preferences, # Eliminado
                'experiencias_seleccionadas': experiencias,
                'service_distribution': self._analyze_service_distribution(servicios),
                'budget_info': {
                    'total_budget': itinerario_data.get('presupuesto', 0),
                    'budget_utilization': itinerario_data.get('utilizacion_presupuesto', 0)
                },
                'request_info': {
                    'ip_address': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'timestamp': timezone.now().isoformat()
                }
            }

            # Crear la interacción
            interaction = Interaction.objects.create(
                user_id=user,
                session_id=session_id,
                action=InteractionAction.SAVE_ITINERARY,
                content_type=ContentType.objects.get_for_model(Itinerary),
                object_id=itinerary.itinerary_id,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                metadata=metadata
            )

            logger.info(f"✅ Interacción de guardado registrada: {interaction.interaction_id}")
            return interaction

        except Exception as e:
            logger.error(f"❌ Error al guardar interacción de itinerario: {str(e)}")
            return None

    def _update_user_profile_from_itinerary(self, user, itinerario_data):
        """Actualiza el perfil del usuario basado en el itinerario guardado (incluye experiencias)"""
        try:
            if not user.is_authenticated:
                return

            servicios = itinerario_data.get('servicios', {})
            # 'preferences' ya no se usa
            experiencias = itinerario_data.get('experiencias', [])

            # 1. Actualizar intereses del usuario (incluyendo experiencias)
            # Volvemos a pasar solo 'servicios' y 'experiencias'
            self._update_user_interests(user, servicios, experiencias)

            logger.info(f"✅ Perfil actualizado para usuario: {user.email}")

        except Exception as e:
            logger.error(f"❌ Error actualizando perfil de usuario: {str(e)}")

    def _update_user_interests(self, user, servicios, experiencias):
        """Actualiza los intereses del usuario basado en servicios y EXPERIENCIAS"""
        try:
            # Volver a la versión sin 'lugares'
            service_to_interest = {
                'actividades': ['Aventura', 'Cultura', 'Naturaleza', 'Deportes', 'Urbano', 'Compras', 'Relax'], # Combinado
                # 'lugares': ['Cultura', 'Urbano', 'Compras', 'Relax', 'Naturaleza'], -> Eliminado
                'eventos': ['Cultura', 'Música', 'Arte', 'Deportes'],
                'hospedaje': ['Lujo', 'Económico', 'Aventura', 'Relax'],
                'comida': ['Gastronomía', 'Local', 'Internacional'],
                'transporte': ['Aventura', 'Confort', 'Económico']
            }

            experiencia_to_interest = {
                'Aventura': ['Aventura', 'Naturaleza', 'Deportes', 'Extremo'],
                'Cultura': ['Cultura', 'Arte', 'Historia', 'Tradiciones'],
                'Gastronomía': ['Gastronomía', 'Local', 'Vinos', 'Culinario'],
                'Relax': ['Relax', 'Bienestar', 'Spa', 'Tranquilidad'],
                'Naturaleza': ['Naturaleza', 'Ecoturismo', 'Aire Libre', 'Aventura'],
                'Urbano': ['Ciudad', 'Compras', 'Entretenimiento', 'Moderno'],
                'Familiar': ['Familia', 'Niños', 'Diversión', 'Seguro'],
                'Romántico': ['Romántico', 'Lujo', 'Intimidad', 'Relax']
            }

            detected_interests = set()

            # 1. Analizar distribución de servicios
            for service_type, service_list in servicios.items(): # Renombrado a service_list
                if service_type in service_to_interest and service_list: # Chequear si la lista no está vacía
                    detected_interests.update(service_to_interest[service_type])

            # 2. Analizar EXPERIENCIAS seleccionadas
            for experiencia in experiencias:
                if experiencia in experiencia_to_interest:
                    detected_interests.update(experiencia_to_interest[experiencia])
                    detected_interests.update(experiencia_to_interest[experiencia])

            # Actualizar pesos de intereses
            from apps.users.models import Interest, UserInterest
            from decimal import Decimal

            for interest_name in detected_interests:
                interest, created = Interest.objects.get_or_create(name=interest_name)

                user_interest, created = UserInterest.objects.get_or_create(
                    user_id=user,
                    interest_id=interest,
                    defaults={'weight': Decimal('0.1')}
                )

                if not created:
                    # Incrementar peso
                    if any(exp in interest_name for exp in experiencias):
                        increment = Decimal('0.08')
                    else:
                        increment = Decimal('0.05')

                    new_weight = min(user_interest.weight + increment, Decimal('1.0'))
                    user_interest.weight = new_weight
                    user_interest.save()

        except Exception as e:
            logger.error(f"❌ Error actualizando intereses: {str(e)}")

    def _update_traveler_type(self, user, servicios, experiencias, traveler_type_used):
        """Actualiza el traveler type basado en patrones detectados (incluye experiencias)"""
        try:
            from apps.users.models import TravelerType

            # Analizar patrones para determinar traveler type
            # Volvemos a pasar solo 'servicios' y 'experiencias'
            service_patterns = self._analyze_travel_patterns(servicios, experiencias)

            # Buscar traveler type que coincida con los patrones
            traveler_type = self._find_matching_traveler_type(service_patterns, traveler_type_used)

            if traveler_type and traveler_type != user.traveler_type_id:
                user.traveler_type_id = traveler_type
                user.save()

                logger.info(f"✅ Traveler type actualizado: {traveler_type.name}")

        except Exception as e:
            logger.error(f"❌ Error actualizando traveler type: {str(e)}")

    def _analyze_travel_patterns(self, servicios, experiencias):
        """Analiza patrones de viaje desde servicios y EXPERIENCIAS"""
        patterns = {
            'adventure_score': 0, 'cultural_score': 0, 'luxury_score': 0,
            'budget_score': 0, 'relax_score': 0, 'gastronomy_score': 0,
            'nature_score': 0, 'family_score': 0, 'romantic_score': 0
        }

        # Volver a la versión sin 'lugares'
        type_scores = {
            'actividades': {'adventure_score': 2, 'cultural_score': 2, 'nature_score': 1, 'relax_score': 1}, # Combinado
            # 'lugares': {'cultural_score': 2, 'nature_score': 1, 'relax_score': 1}, -> Eliminado
            'eventos': {'cultural_score': 2},
            'hospedaje': {'luxury_score': 1, 'relax_score': 1},
            'comida': {'cultural_score': 1, 'gastronomy_score': 2},
            'transporte': {'adventure_score': 1}
        }

        experiencia_scores = {
            'Aventura': {'adventure_score': 3, 'nature_score': 2},
            'Cultura': {'cultural_score': 3},
            'Gastronomía': {'gastronomy_score': 3},
            'Relax': {'relax_score': 3},
            'Naturaleza': {'nature_score': 3, 'adventure_score': 1},
            'Urbano': {'cultural_score': 1, 'luxury_score': 1},
            'Familiar': {'family_score': 3},
            'Romántico': {'romantic_score': 3, 'luxury_score': 2, 'relax_score': 1}
        }

        # 1. Puntajes de servicios
        for service_type, service_list in servicios.items(): # Renombrado
            if service_type in type_scores and service_list: # Chequear lista
                for pattern, score in type_scores[service_type].items():
                    patterns[pattern] += score * len(service_list)

        # 2. Puntajes de EXPERIENCIAS
        for experiencia in experiencias:
            if experiencia in experiencia_scores:
                for pattern, score in experiencia_scores[experiencia].items():
                    patterns[pattern] += score * 2

        return patterns

    def _find_matching_traveler_type(self, patterns, traveler_type_used):
        """Encuentra el traveler type que mejor coincide con los patrones"""
        from apps.users.models import TravelerType

        traveler_types = TravelerType.objects.filter(is_active=True)
        best_match = None
        best_score = 0

        # PRIMERO: Si tenemos un traveler_type_used, darle prioridad
        if traveler_type_used:
            try:
                used_type = TravelerType.objects.get(name=traveler_type_used)
                # Verificar que tenga un match razonable
                used_score = self._calculate_traveler_type_match(used_type, patterns)
                if used_score > 0.3:  # Umbral más bajo para el tipo usado
                    return used_type
            except TravelerType.DoesNotExist:
                pass

        # Si no hay tipo usado o no coincide, buscar el mejor match
        for tt in traveler_types:
            score = self._calculate_traveler_type_match(tt, patterns)
            if score > best_score:
                best_score = score
                best_match = tt

        return best_match if best_score > 0.5 else None

    def _calculate_traveler_type_match(self, traveler_type, patterns):
        """Calcula qué tan bien coincide un traveler type con los patrones"""
        name_lower = traveler_type.name.lower()
        description_lower = (traveler_type.description or "").lower()

        score = 0

        # Mapeo de patrones a términos de búsqueda
        pattern_terms = {
            'adventure_score': ['aventur', 'extrem', 'deporte', 'activo'],
            'cultural_score': ['cultur', 'arte', 'historia', 'museo', 'tradicion'],
            'luxury_score': ['lujo', 'premium', 'exclusiv', 'confort'],
            'budget_score': ['económic', 'budget', 'económico', 'ahorro'],
            'relax_score': ['relax', 'tranquilo', 'descanso', 'spa', 'bienestar'],
            'gastronomy_score': ['gastronom', 'comida', 'culinari', 'vinos'],
            'nature_score': ['naturaleza', 'ecoturismo', 'aire libre', 'parque'],
            'family_score': ['familiar', 'familia', 'niños', 'infantil'],
            'romantic_score': ['romántic', 'pareja', 'luna de miel', 'intimidad']
        }

        # Calcular score basado en patrones
        total_pattern_score = sum(patterns.values()) # Normalizar score
        if total_pattern_score == 0: return 0.0

        for pattern, terms in pattern_terms.items():
            pattern_value = patterns.get(pattern, 0)
            if pattern_value > 0:
                for term in terms:
                    if term in name_lower or term in description_lower:
                        # Ponderar más si el término está en el nombre
                        weight = 1.5 if term in name_lower else 1.0
                        score += (pattern_value / total_pattern_score) * weight


        return min(score, 1.0)  # Asegurar que esté entre 0 y 1

    def _analyze_service_distribution(self, servicios):
        """Analiza la distribución de servicios para el perfilado"""
        try:
            distribution = {}
            total_services = sum(len(service_list) for service_list in servicios.values()) # Renombrado

            for service_type, service_list in servicios.items(): # Renombrado
                if total_services > 0:
                    percentage = (len(service_list) / total_services) * 100
                    distribution[service_type] = {
                        'count': len(service_list),
                        'percentage': round(percentage, 2)
                    }
                else:
                    distribution[service_type] = {
                        'count': 0,
                        'percentage': 0.0
                    }

            return distribution
        except Exception as e:
            logger.error(f"Error analizando distribución de servicios: {str(e)}")
            return {}

    def _create_itinerary_items(self, itinerary, itinerario_data):
        """
        Crea los items del itinerario usando operaciones BULK.
        """
        items_para_crear = []
        
        backend_type_to_model_config = {
            'accommodation': { 'content_type_model': 'accommodationservice', 'app_label': 'experiences' },
            'dining': { 'content_type_model': 'place', 'app_label': 'location' },
            'activity': { 'content_type_model': 'activityservice', 'app_label': 'experiences' },
            'place_activity': { 'content_type_model': 'place', 'app_label': 'location' },
            'event': { 'content_type_model': 'event', 'app_label': 'experiences' }
        }
        
        # --- 1. OBTENER TODOS LOS CONTENT TYPES DE UNA VEZ ---
        app_labels = set(c['app_label'] for c in backend_type_to_model_config.values())
        models = set(c['content_type_model'] for c in backend_type_to_model_config.values())
        
        content_types_qs = ContentType.objects.filter(
            app_label__in=list(app_labels), 
            model__in=list(models)
        )
        
        # Crear un cache en memoria para acceso instantáneo
        content_type_cache = {
            f"{ct.app_label}:{ct.model}": ct for ct in content_types_qs
        }
        
        if not content_type_cache:
            logger.error("❌ No se pudo cargar ningún ContentType. Verifique 'backend_type_to_model_config'.")
            return []

        servicios = itinerario_data.get('servicios', {})

        # --- 2. PREPARAR LOS ITEMS (SIN CREARLOS) ---
        for servicio_tipo, items_servicio in servicios.items():
            if not items_servicio:
                continue

            for idx, item_data in enumerate(items_servicio):
                try:
                    backend_type = item_data.get('backend_type')
                    if not backend_type:
                        logger.warning(f"⚠️ Item {item_data.get('nombre')} no tiene 'backend_type'. Saltando.")
                        continue

                    service_config = backend_type_to_model_config.get(backend_type)
                    if not service_config:
                        logger.warning(f"⚠️ Tipo de backend no mapeado al guardar: {backend_type}")
                        continue
                    
                    # --- OBTENER CONTENT TYPE DESDE CACHE (INSTANTÁNEO) ---
                    cache_key = f"{service_config['app_label']}:{service_config['content_type_model']}"
                    content_type = content_type_cache.get(cache_key)
                    
                    if not content_type:
                        logger.error(f"❌ ContentType no encontrado EN CACHE: {cache_key}")
                        continue
                    
                    object_id_str = item_data.get('id')
                    try:
                        object_id = uuid.UUID(str(object_id_str))
                    except (ValueError, TypeError, AttributeError):
                         logger.warning(f"⚠️ ID inválido o nulo para {item_data.get('nombre')}: '{object_id_str}'. Saltando.")
                         continue
                    
                    scheduled_date = self._parse_date(item_data.get('fecha'))

                    # Añadir a la lista para bulk_create
                    items_para_crear.append(
                        ItineraryItem(
                            itinerary_id=itinerary,
                            content_type=content_type,
                            object_id=object_id,
                            scheduled_date=scheduled_date,
                            estimated_cost=item_data.get('costo', 0),
                            estimated_cost_currency='CLP' 
                        )
                    )

                except Exception as e:
                    logger.error(f"❌ Error procesando item {idx} de {servicio_tipo}: {str(e)}")
                    continue
        
        # --- 3. CREAR TODOS LOS ITEMS EN UNA SOLA CONSULTA ---
        items_creados = []
        if items_para_crear:
            try:
                # bulk_create devuelve los objetos creados (incluyendo sus nuevos PKs)
                items_creados = ItineraryItem.objects.bulk_create(items_para_crear)
                logger.info(f"🎉 Total de items guardados (bulk): {len(items_creados)}")
            except Exception as e:
                 logger.error(f"❌ Error en ItineraryItem.objects.bulk_create: {str(e)}", exc_info=True)
        
        return items_creados



    def _find_service_object_id(self, item_data, service_config):
        """
        Busca o determina el object_id para el servicio.
        NOTA: Esta función asume que el tipo de modelo es fijo por service_config.
              Necesita modificarse si 'actividades' puede contener Place y ActivityService.
        """
        model_class = service_config['model_class']
        id_field = service_config['id_field']

        try:
            # logger.debug(f"🔍 Buscando object_id para: {item_data.get('nombre', 'Sin nombre')} usando {model_class.__name__}")
            # logger.debug(f"   ID en datos: {item_data.get('id', 'No disponible')}")

            # OPCIÓN 1: Usar el ID proporcionado en los datos (si es UUID válido)
            item_id_str = item_data.get('id')
            if item_id_str:
                try:
                    service_uuid = uuid.UUID(str(item_id_str))
                    # VERIFICAR que el servicio existe en la base de datos
                    # Usar **kwargs para construir el filtro dinámicamente
                    if model_class.objects.filter(**{id_field: service_uuid}).exists():
                        # logger.debug(f"   ✅ Usando UUID existente: {service_uuid}")
                        return service_uuid
                    else:
                        logger.warning(f"   ⚠️ UUID {service_uuid} no existe en {model_class.__name__}, pero se usará.")
                        # Considerar si realmente quieres guardar un item que apunta a un objeto inexistente
                        return service_uuid
                except (ValueError, AttributeError, TypeError) as e: # Añadir TypeError
                    logger.warning(f"   ❌ ID '{item_id_str}' no es un UUID válido: {e}")
                    # ¿Qué hacer si el ID no es UUID? Podría ser un ID antiguo, o error.
                    # Por ahora, continuamos para ver si hay otras formas de encontrarlo, o fallamos.
                    pass # Continuar a otras opciones si las hubiera

            # Por ahora, si no hay ID válido, no podemos encontrarlo.
            logger.warning(f"   ❌ No se pudo determinar un object_id válido para '{item_data.get('nombre')}'")
            return None


        except Exception as e:
            logger.error(f"❌ Error inesperado en _find_service_object_id: {str(e)}")
            return None

    def _parse_date(self, date_string):
        """Convierte string de fecha a datetime object"""
        if not date_string:
            # logger.warning("Fecha vacía recibida, usando timezone.now()")
            return timezone.now() # Usar timezone.now() para que sea aware

        try:
            # Intentar formato ISO con zona horaria Z o +HH:MM
            dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            # Asegurar que sea aware
            if not timezone.is_aware(dt):
                 # Asumir UTC si no tiene offset
                 dt = timezone.make_aware(dt, timezone.utc)
            return dt
        except ValueError:
             # Intentar otros formatos comunes si falla ISO
             for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                  try:
                       dt = datetime.strptime(date_string, fmt)
                       # Hacerlo aware usando la zona por defecto de Django
                       return timezone.make_aware(dt, timezone.get_current_timezone())
                  except ValueError:
                       pass
        except Exception as e: # Capturar otros errores inesperados
             logger.error(f"Error inesperado parseando fecha '{date_string}': {e}")


        logger.warning(f"Formato de fecha no reconocido: '{date_string}'. Usando timezone.now().")
        return timezone.now() # Fallback final


class UserItinerariesView(generics.ListAPIView):
    """Obtiene todos los itinerarios del usuario autenticado"""
    serializer_class = ItineraryWithItemsSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Itinerary.objects.none()

        collaborator_itineraries = ItineraryCollaborator.objects.filter(
            user_id=user
        ).values_list('itinerary_id', flat=True)

        # OPTIMIZACIÓN: Usar Prefetch con select_related para coordenadas
        # NOTA: La pre-carga del GenericForeignKey ('reservable')
        # es compleja y generalmente se hace en el Serializer
        # o pre-cargando cada modelo por separado.
        # Dejamos la optimización simple aquí.
        return Itinerary.objects.filter(
            itinerary_id__in=collaborator_itineraries
        ).prefetch_related(
            Prefetch(
                'itineraryitem_set',
                queryset=ItineraryItem.objects.select_related('content_type')
                # Si 'ItineraryWithItemsSerializer' pre-carga 'reservable',
                # podría causar errores.
            )
        ).order_by('-created_at')

class ItineraryDetailView(generics.RetrieveAPIView):
    """Obtiene el detalle de un itinerario específico"""
    serializer_class = ItineraryWithItemsSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Itinerary.objects.none()

        collaborator_itineraries = ItineraryCollaborator.objects.filter(
            user_id=user
        ).values_list('itinerary_id', flat=True)

        # OPTIMIZACIÓN MEJORADA para el detalle
        return Itinerary.objects.filter(
            itinerary_id__in=collaborator_itineraries
        ).prefetch_related(
            Prefetch(
                'itineraryitem_set',
                queryset=ItineraryItem.objects.select_related('content_type')
                # Aquí también, el prefetch del GFK se maneja mejor en otro lugar
                # o con 'prefetch_related_objects'
            )
        )

    lookup_field = 'itinerary_id'

class DebugItineraryView(APIView):
    def get(self, request, itinerary_id):
        """Vista temporal para debuggear un itinerario específico"""
        try:
            # Usar prefetch_related para eficiencia al acceder a 'reservable'
            itinerary = Itinerary.objects.prefetch_related(
                 Prefetch(
                      'itineraryitem_set',
                      queryset=ItineraryItem.objects.select_related('content_type').prefetch_related('reservable') 
                 )
            ).get(itinerary_id=itinerary_id)


            debug_data = {
                'itinerary': {
                    'id': str(itinerary.itinerary_id),
                    'name': itinerary.name,
                    'items_count': itinerary.itineraryitem_set.count() # Usar el prefetch count
                },
                'items': []
            }

            for item in itinerary.itineraryitem_set.all(): # Iterar sobre el prefetch
                item_data = {
                    'item_id': str(item.item_id),
                    'content_type': item.content_type.model,
                    'object_id': str(item.object_id),
                    'scheduled_date': item.scheduled_date.isoformat() if item.scheduled_date else None,
                    'estimated_cost': float(item.estimated_cost)
                }

                # Intentar obtener el objeto relacionado usando el 'reservable' prefetchado
                try:
                    target_object = item.reservable 
                    if target_object:
                        item_data['service_name'] = getattr(target_object, 'name', f'Objeto sin nombre ({type(target_object).__name__})')
                        # Añadir más detalles si es necesario
                        if isinstance(target_object, Place):
                             item_data['place_type'] = target_object.type
                        elif isinstance(target_object, ActivityService):
                             item_data['activity_duration'] = target_object.duration_minutes

                    else:
                        # Esto podría pasar si el objeto fue borrado
                        item_data['service_name'] = f'Objeto relacionado (ID: {item.object_id}) no encontrado o es None'
                except Exception as e:
                    # Capturar cualquier error al acceder al objeto relacionado
                    item_data['service_name'] = f'Error al acceder al objeto relacionado: {str(e)}'

                debug_data['items'].append(item_data)

            return Response(debug_data)

        except Itinerary.DoesNotExist:
            return Response({'error': 'Itinerario no encontrado'}, status=404)
        except Exception as e:
             logger.error(f"Error en DebugItineraryView: {e}", exc_info=True)
             return Response({'error': f"Error interno: {e}"}, status=500)