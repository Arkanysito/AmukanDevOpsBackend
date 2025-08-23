from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.travel.itineray_generator import itinerary_preview

class ItineraryPreviewView(APIView):
    def post(self, request):
        data = request.data
        destino = data.get("destino")
        desde = data.get("desde")
        hasta = data.get("hasta")

        try:
            presupuesto = int(data.get("presupuesto", 0))
            cantidad_personas = int(data.get("cantidad_personas", 1))
        except ValueError:
            return Response({"error": "Presupuesto y cantidad_personas deben ser números"}, status=status.HTTP_400_BAD_REQUEST)

        if not all([destino, desde, hasta]):
            return Response({"error": "Faltan campos obligatorios"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            desde = datetime.fromisoformat(desde)
            hasta = datetime.fromisoformat(hasta)
        except ValueError:
            return Response({"error": "Formato de fecha inválido"}, status=status.HTTP_400_BAD_REQUEST)

        itinerarios = itinerary_preview(request, destino, desde, hasta, presupuesto, cantidad_personas)

        if not itinerarios:
            return Response({"message": "No se pudo generar un itinerario con los parámetros dados"}, status=status.HTTP_204_NO_CONTENT)

        def get_coordinates(obj):
            point = getattr(obj, "coordinates", None) or getattr(getattr(obj, "place_id", None), "coordinates", None)
            return getattr(point, "wkt", None) if point else None

        response_itinerarios = []

        for itinerario in itinerarios:
            servicios = {
                "hospedaje": [],
                "transporte": [],
                "comida": [],
                "actividades": [],
                "eventos": []
            }
            total_estimado = 0

            for item in itinerario["items"]:
                objeto = item.objeto
                tipo = getattr(objeto, "tipo_servicio", item.tipo)
                servicio = {
                    "nombre": getattr(objeto, "name", getattr(objeto, "title", "Sin nombre")),
                    "descripcion": getattr(objeto, "descripcion", ""),
                    "rating": item.rating,
                    "fecha": item.fecha.isoformat() if item.fecha else None,
                    "costo": item.costo,
                    "coordenadas": get_coordinates(objeto)
                }
                total_estimado += item.costo

                tipo_map = {
                    "hospedaje": "hospedaje",
                    "alojamiento": "hospedaje",
                    "comida": "comida",
                    "actividad": "actividades",
                    "actividades": "actividades",
                    "evento": "eventos",
                    "eventos": "eventos",
                    "transporte": "transporte"
                }
                tipo_normalizado = tipo_map.get(tipo, "eventos")
                servicios[tipo_normalizado].append(servicio)

            response_itinerarios.append({
                "titulo": f"Itinerario para {destino}",
                "duracion": f"{(hasta - desde).days} días / {(hasta - desde).days - 1} noches",
                "cantidad_personas": cantidad_personas,
                "presupuesto": total_estimado,
                "servicios": servicios
            })

        

        return Response(response_itinerarios, status=status.HTTP_200_OK)