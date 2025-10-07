from django.utils import timezone
from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.travel.itineray_generator import generate_optimized_itineraries
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
from apps.experiences.models import Event, AccommodationService, ActivityService, TransportService
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
        preferences = data.get("preferences", {})

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
            
            presupuesto = float(presupuesto)
            cantidad_personas = int(cantidad_personas)
            
        except (ValueError, TypeError) as e:
            return Response({"error": f"Parámetros inválidos: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Generar itinerarios optimizados
        itinerarios = generate_optimized_itineraries(
            request, destino, desde, hasta, presupuesto, cantidad_personas, preferences
        )

        # GUARDAR LA BÚSQUEDA EN LA BASE DE DATOS
        self._save_search_interaction(request, destino, desde, hasta, presupuesto, cantidad_personas, preferences, itinerarios)

        if not itinerarios:
            return Response({
                "message": "No se pudo generar un itinerario con los parámetros dados",
                "suggestion": "Intente con un destino diferente o verifique la disponibilidad de servicios"
            }, status=status.HTTP_204_NO_CONTENT)

        # Asegurarse de que tenemos la estructura correcta
        if isinstance(itinerarios, dict) and 'itineraries' in itinerarios:
            response_data = self._format_itineraries_for_frontend(itinerarios, destino, desde, hasta, cantidad_personas)
        else:
            # Si viene en otro formato, crear la estructura esperada
            response_data = self._format_itineraries_for_frontend(
                {'itineraries': itinerarios}, destino, desde, hasta, cantidad_personas
            )
        
        return Response(response_data, status=status.HTTP_200_OK)

    def _save_search_interaction(self, request, destino, desde, hasta, presupuesto, cantidad_personas, preferences, itinerarios):
        """Guarda la búsqueda en la base de datos como una interacción"""
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
                    'preferences': preferences
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
            print(f"Error al guardar interacción de búsqueda: {str(e)}")
            return None

    def _get_session_id(self, request):
        """Obtiene o crea un ID de sesión para el usuario"""
        if not request.session.session_key:
            request.session.create()
        return request.session.session_key

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
            
            valid_costs = [cost for cost in costs if cost and cost > 0]
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
        else:
            itinerarios_list = itinerarios
        
        for idx, itinerario in enumerate(itinerarios_list):
            servicios = {
                "hospedaje": [],
                "transporte": [],
                "comida": [],
                "actividades": [],
                "eventos": []
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
                    if tipo_frontend:
                        servicios[tipo_frontend].append(servicio_formateado)

                # Calcular duración
                if dias_totales == 1:
                    duracion = "1 día"
                else:
                    duracion = f"{dias_totales} días / {dias_totales - 1} noches"

                formatted_itineraries.append({
                    "id": idx + 1,
                    "titulo": f"Itinerario {idx+1} para {destino} ({itinerario.get('strategy', 'standard')})",
                    "duracion": duracion,
                    "cantidad_personas": cantidad_personas,
                    "presupuesto": float(itinerario["total_cost"]),
                    "utilizacion_presupuesto": float(itinerario.get("budget_utilization", 0)),
                    "servicios": servicios
                })
        
        return formatted_itineraries
    
    def _obtener_numero_dia(self, item, start_date):
        """Obtiene el número de día basado en la fecha del item"""
        item_date = item.get('date')
        if not item_date:
            return 1  # Default al primer día
        
        if isinstance(item_date, str):
            item_date = datetime.fromisoformat(item_date.replace('Z', '+00:00'))
        
        # Calcular diferencia de días
        diferencia = (item_date.date() - start_date.date()).days
        return max(1, diferencia + 1)
    
    def _map_service_type_to_frontend(self, backend_type):
        """Mapea los tipos del backend a los que espera el frontend"""
        type_mapping = {
            'accommodation': 'hospedaje',
            'dining': 'comida',
            'activity': 'actividades',
            'transport': 'transporte',
            'event': 'eventos'
        }
        return type_mapping.get(backend_type)
    
    def _format_service_item(self, item):
        """Formatea un item de servicio para la respuesta"""
        service = item.get('service')
        
        if service is None:
            # Servicio genérico (fallback)
            formatted_service = {
                "nombre": item.get('description', 'Servicio'),
                "descripcion": item.get('description', 'Servicio incluido en el itinerario'),
                "rating": 0.0,
                "fecha": item['date'].isoformat() if 'date' in item else None,
                "costo": float(item['cost']),
                "coordenadas": self._get_coordinates(service),
                "duracion": item.get('duration_hours'),
                "tipo_comida": item.get('meal_type')
            }
        else:
            # Servicio de la base de datos
            formatted_service = {
                "id": str(getattr(service, 'service_id', getattr(service, 'place_id', getattr(service, 'event_id', '')))),
                "nombre": getattr(service, 'name', 'Servicio'),
                "descripcion": getattr(service, 'description', ''),
                "rating": float(getattr(service, 'rating', 0.0)),
                "fecha": item['date'].isoformat() if 'date' in item else None,
                "costo": float(item['cost']),
                "coordenadas": self._get_coordinates(service),
                "duracion": item.get('duration_hours'),
                "tipo_comida": item.get('meal_type')
            }
        
        # Para eventos, agregar información específica
        if item.get('type') == 'event' and hasattr(service, 'start_date'):
            formatted_service.update({
                "fecha_inicio": service.start_date.isoformat() if service.start_date else None,
                "fecha_fin": service.end_date.isoformat() if service.end_date else None,
                "es_evento": True
            })
        
        # Asegurarse de que las coordenadas estén en formato WKT
        if formatted_service["coordenadas"] and isinstance(formatted_service["coordenadas"], dict):
            point = formatted_service["coordenadas"]
            formatted_service["coordenadas"] = f"POINT({point['lng']} {point['lat']})"
        
        return formatted_service
    
    def _get_coordinates(self, obj):
        """Obtiene las coordenadas de un objeto en formato consistente"""
        if obj is None:
            return None
            
        # Intentar diferentes formas de obtener coordenadas
        coordinates = None
        
        # 1. Coordenadas directas del objeto
        if hasattr(obj, 'coordinates') and obj.coordinates:
            coordinates = obj.coordinates
        # 2. Coordenadas a través de place_id
        elif hasattr(obj, 'place_id') and hasattr(obj.place_id, 'coordinates') and obj.place_id.coordinates:
            coordinates = obj.place_id.coordinates
        
        # Convertir a formato consistente
        if coordinates:
            if hasattr(coordinates, 'x') and hasattr(coordinates, 'y'):
                return {"lat": coordinates.y, "lng": coordinates.x}
            elif hasattr(coordinates, 'wkt'):
                return coordinates.wkt
        
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
                
                return Response({
                    "message": "Itinerario guardado exitosamente",
                    "itinerary_id": str(itinerary.itinerary_id),
                    "name": itinerary.name,
                    "items_count": len(items_creados),
                    "items_by_type": {k: len(v) for k, v in data['itinerario_data'].get('servicios', {}).items()}
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"❌ Error al guardar itinerario: {str(e)}")
            return Response(
                {"error": f"Error al guardar itinerario: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _create_itinerary_items(self, itinerary, itinerario_data):
        """Crea los items del itinerario usando tus modelos reales"""
        items_creados = []
        
        service_type_mapping = {
            'hospedaje': {
                'content_type_model': 'accommodationservice',
                'model_class': AccommodationService,
                'id_field': 'service_id'
            },
            'comida': {
                'content_type_model': 'place',
                'model_class': Place, 
                'id_field': 'place_id'
            },
            'actividades': {
                'content_type_model': 'activityservice',
                'model_class': ActivityService,
                'id_field': 'service_id'
            },
            'transporte': {
                'content_type_model': 'transportservice', 
                'model_class': TransportService,
                'id_field': 'service_id'
            },
            'eventos': {
                'content_type_model': 'event',
                'model_class': Event,
                'id_field': 'event_id'
            }
        }
        
        servicios = itinerario_data.get('servicios', {})
        
        for servicio_tipo, items_servicio in servicios.items():
            service_config = service_type_mapping.get(servicio_tipo)
            if not service_config:
                logger.warning(f"⚠️ Tipo de servicio no mapeado: {servicio_tipo}")
                continue
            
            try:
                content_type = ContentType.objects.get(model=service_config['content_type_model'])
            except ContentType.DoesNotExist:
                logger.error(f"❌ ContentType no encontrado: {service_config['content_type_model']}")
                continue
            
            for idx, item_data in enumerate(items_servicio):
                try:
                    # Buscar el objeto real en la base de datos
                    object_id = self._find_service_object_id(item_data, service_config)
                    
                    if not object_id:
                        logger.warning(f"⚠️ No se pudo encontrar object_id para item: {item_data.get('nombre', 'Sin nombre')}")
                        continue
                    
                    # Preparar fecha programada
                    scheduled_date = self._parse_date(item_data.get('fecha'))
                    
                    # Crear el itinerary item
                    item = ItineraryItem.objects.create(
                        itinerary_id=itinerary,
                        content_type=content_type,
                        object_id=object_id,
                        scheduled_date=scheduled_date,
                        estimated_cost=item_data.get('costo', 0),
                        estimated_cost_currency='USD'
                    )
                    
                    items_creados.append(item)
                    logger.info(f"✅ Item guardado: {item_data.get('nombre', 'Sin nombre')} - ObjectID: {object_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Error guardando item {idx} de {servicio_tipo}: {str(e)}")
                    continue
        
        logger.info(f"🎉 Total de items guardados: {len(items_creados)}")
        return items_creados
    

    
    def _find_service_object_id(self, item_data, service_config):
        """
        Busca o determina el object_id para el servicio.
        IMPORTANTE: El mismo servicio puede estar en múltiples itinerarios.
        """
        model_class = service_config['model_class']
        id_field = service_config['id_field']
        
        try:
            # DEBUG: Ver qué datos tenemos
            logger.info(f"🔍 Buscando object_id para: {item_data.get('nombre', 'Sin nombre')}")
            logger.info(f"   ID en datos: {item_data.get('id', 'No disponible')}")
            
            # OPCIÓN 1: Usar el ID proporcionado en los datos (si es UUID válido)
            if 'id' in item_data and item_data['id']:
                try:
                    service_uuid = uuid.UUID(str(item_data['id']))
                    # VERIFICAR que el servicio existe en la base de datos
                    if model_class.objects.filter(**{id_field: service_uuid}).exists():
                        logger.info(f"   ✅ Usando UUID existente: {service_uuid}")
                        return service_uuid
                    else:
                        logger.warning(f"   ⚠️ UUID no existe en BD, pero lo usaremos: {service_uuid}")
                        return service_uuid
                except (ValueError, AttributeError) as e:
                    logger.warning(f"   ❌ UUID inválido: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error en _find_service_object_id: {str(e)}")
            # Fallback: generar UUID
            return uuid.uuid4()
    
    def _parse_date(self, date_string):
        """Convierte string de fecha a datetime object"""
        if not date_string:
            return datetime.now()
        
        try:
            if 'T' in date_string:
                return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            else:
                return datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            return datetime.now()

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
        return Itinerary.objects.filter(
            itinerary_id__in=collaborator_itineraries
        ).prefetch_related(
            Prefetch(
                'itineraryitem_set',
                queryset=ItineraryItem.objects.select_related('content_type')
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
            )
        )
    
    lookup_field = 'itinerary_id'

# agregar temporalmente
class DebugItineraryView(APIView):
    def get(self, request, itinerary_id):
        """Vista temporal para debuggear un itinerario específico"""
        try:
            itinerary = Itinerary.objects.get(itinerary_id=itinerary_id)
            
            # Obtener items manualmente
            items = ItineraryItem.objects.filter(itinerary_id=itinerary)
            
            debug_data = {
                'itinerary': {
                    'id': str(itinerary.itinerary_id),
                    'name': itinerary.name,
                    'items_count': items.count()
                },
                'items': []
            }
            
            for item in items:
                item_data = {
                    'item_id': str(item.item_id),
                    'content_type': item.content_type.model,
                    'object_id': str(item.object_id),
                    'scheduled_date': item.scheduled_date.isoformat(),
                    'estimated_cost': float(item.estimated_cost)
                }
                
                # Intentar obtener el objeto relacionado
                try:
                    if item.reservable:
                        item_data['service_name'] = getattr(item.reservable, 'name', 'No name')
                    else:
                        item_data['service_name'] = 'Reservable is None'
                except Exception as e:
                    item_data['service_name'] = f'Error: {str(e)}'
                
                debug_data['items'].append(item_data)
            
            return Response(debug_data)
            
        except Itinerary.DoesNotExist:
            return Response({'error': 'Itinerario no encontrado'}, status=404)