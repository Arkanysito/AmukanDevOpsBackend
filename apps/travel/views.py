from django.utils import timezone
from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.travel.itineray_generator import generate_optimized_itineraries

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

        if not itinerarios:
            return Response({
                "message": "No se pudo generar un itinerario con los parámetros dados",
                "suggestion": "Intente con un destino diferente o verifique la disponibilidad de servicios"
            }, status=status.HTTP_204_NO_CONTENT)

        # Formatear respuesta para el frontend
        response_data = self._format_itineraries_for_frontend(itinerarios, destino, desde, hasta, cantidad_personas)
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def _format_itineraries_for_frontend(self, itinerarios, destino, desde, hasta, cantidad_personas):
        """Formatea los itinerarios agregando número de día a cada servicio"""
        formatted_itineraries = []
        
        dias_totales = max(1, (hasta - desde).days)
        
        for idx, itinerario in enumerate(itinerarios):
            servicios = {
                "hospedaje": [],
                "transporte": [],
                "comida": [],
                "actividades": [],
                "eventos": []
            }
            
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
        return max(1, diferencia + 1)  # Día 1, 2, 3, ...
    
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