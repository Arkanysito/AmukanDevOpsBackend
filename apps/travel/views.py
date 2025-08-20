from datetime import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.travel.itineray_generator import itinnerary_preview

class ItineraryPreviewView(APIView):
    def post(self, request):
        data = request.data
        destino = data.get("destino")
        desde = data.get("desde")
        hasta = data.get("hasta")
        presupuesto = data.get("presupuesto", 0)
        cantidad_personas = data.get("cantidad_personas", 1)

        if not all([destino, desde, hasta]):
            return Response({"error": "Faltan campos obligatorios"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            desde = datetime.fromisoformat(desde)
            hasta = datetime.fromisoformat(hasta)
        except ValueError:
            return Response({"error": "Formato de fecha inválido"}, status=status.HTTP_400_BAD_REQUEST)

        items = itinnerary_preview(destino, desde, hasta, presupuesto, cantidad_personas)

        if not items:
            return Response({"message": "No se pudo generar un itinerario con los parámetros dados"}, status=status.HTTP_204_NO_CONTENT)

        def get_coordinates(obj):
            point = getattr(obj, "coordinates", None) or getattr(getattr(obj, "place_id", None), "coordinates", None)
            return getattr(point, "wkt", None) if point else None

        servicios = {
            "hospedaje": [],
            "transporte": [],
            "comida": [],
            "actividades": [],
            "eventos": []
        }

        for item in items:
            tipo = getattr(item.objeto, "tipo_servicio", item.tipo)
            servicio = {
                "nombre": getattr(item.objeto, "name", getattr(item.objeto, "title", "Sin nombre")),
                "descripcion": getattr(item.objeto, "descripcion", ""),
                "rating": getattr(item.objeto, "rating", None),
                "fecha": item.fecha.isoformat(),
                "costo": item.costo,
                "coordenadas": get_coordinates(item.objeto)
            }
            if tipo in servicios:
                servicios[tipo].append(servicio)
            else:
                servicios["eventos"].append(servicio)  # fallback para tipos desconocidos

        response_data = {
            "titulo": f"Itinerario para {destino}",
            "duracion": f"{(hasta - desde).days} días",
            "presupuesto": presupuesto,
            "cantidad_personas": cantidad_personas,
            "servicios": servicios
        }

        return Response(response_data, status=status.HTTP_200_OK)