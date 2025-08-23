from datetime import timedelta
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db.models import Q
from apps.experiences.models import AccommodationService, Event, ActivityService
from apps.location.models import Place, Zone
from apps.tracking.models import Interaction
from apps.core.constants import InteractionAction
import uuid
from collections import namedtuple

def itinerary_preview(request, destino, desde, hasta, presupuesto, cantidad_personas):
    Item = namedtuple("Item", ["objeto", "fecha", "costo", "tipo", "rating"])

    dias = (hasta - desde).days
    if dias <= 0:
        return []

    itinerarios = []  # lista de itinerarios (máximo 5)
    zona = Zone.objects.filter(name__icontains=destino).first()
    if not zona:
        return []

    # Buscar alojamientos disponibles
    alojamientos = AccommodationService.objects.filter(
        place_id__coordinates__within=zona.coordinates
    ).order_by("price")[:5]  # Por ahora limita a 5 más baratos para no sobrecargar

    # Buscar restaurantes disponibles
    restaurantes = Place.objects.filter(
        coordinates__within=zona.coordinates, type="restaurant"
    ).exclude(average_price=None).order_by("average_price")[:20]

    # Actividades
    actividades = ActivityService.objects.filter(
        place_id__coordinates__within=zona.coordinates
    ).order_by("price")[:20]

    # Eventos
    eventos = Event.objects.filter(
        place_id__coordinates__within=zona.coordinates,
        start_date__range=(desde, hasta)
    ).order_by("price")[:20]

    for alojamiento in alojamientos:
        items = []
        total_gasto = 0

        def agregar(objeto, fecha, costo, tipo, rating):
            nonlocal total_gasto
            if total_gasto + costo > presupuesto:
                return False
            items.append(Item(objeto=objeto, fecha=fecha, costo=costo, tipo=tipo, rating=rating))
            total_gasto += costo
            return True

        # Alojamientos
        costo_alojamiento = alojamiento.price * (dias - 1) #dias - 1 = noches
        if not agregar(alojamiento, desde, costo_alojamiento, "hospedaje", alojamiento.rating):
            continue  # si no entra en presupuesto, saltar este itinerario

        # Comidas (mínimo una diaria)
        comidas_agregadas = 0
        for dia in range(dias):
            if comidas_agregadas >= dias:
                break
            if not restaurantes:
                break
            restaurante = restaurantes[comidas_agregadas % len(restaurantes)]
            costo = restaurante.average_price * cantidad_personas
            fecha_comida = desde + timedelta(days=dia)
            if agregar(restaurante, fecha_comida, costo, "comida", restaurante.rating):
                comidas_agregadas += 1

        # Actividades
        for actividad in actividades:
            fecha = getattr(actividad, "start_date", desde)
            costo = actividad.price * cantidad_personas
            agregar(actividad, fecha, costo, "actividades", actividad.rating)

        # Eventos
        for evento in eventos:
            costo = evento.price * cantidad_personas
            agregar(evento, evento.start_date, costo, "eventos", evento.rating)

        itinerarios.append({
            "items": items,
            "total_estimado": total_gasto
        })

        if len(itinerarios) >= 5:
            break

    # Guardar interacción
    Interaction.objects.create(
        user_id = request.user if request.user.is_authenticated else None,
        session_id = request.session.session_key or str(uuid.uuid4()),
        action = InteractionAction.SEARCH,
        ip_address = get_client_ip(request),
        user_agent = request.META.get("HTTP_USER_AGENT", ""),
        metadata={
            "destino": destino,
            "budget": presupuesto,
            "travelers": cantidad_personas,
            "start_date": str(desde),
            "end_date": str(hasta),
            "generated_itineraries": len(itinerarios),
        }
    )

    return itinerarios


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
