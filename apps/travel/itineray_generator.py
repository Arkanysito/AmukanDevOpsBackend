from datetime import timedelta
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db.models import Q
from apps.experiences.models import AccommodationService, Event, ActivityService
from apps.location.models import Place, Zone

def itinnerary_preview(destino, desde, hasta, presupuesto, cantidad_personas, moneda="CLP"):
    from collections import namedtuple
    Item = namedtuple("Item", ["objeto", "fecha", "costo", "tipo"])

    dias = (hasta - desde).days
    if dias <= 0:
        return []

    total_gasto = 0
    items = []

    zona = Zone.objects.filter(name__icontains=destino).first()
    if not zona:
        return []

    def agregar(objeto, fecha, costo, tipo):
        nonlocal total_gasto
        if total_gasto + costo > presupuesto:
            return False
        items.append(Item(objeto=objeto, fecha=fecha, costo=costo, tipo=tipo))
        total_gasto += costo
        return True

    alojamientos = AccommodationService.objects.filter(place_id__coordinates__within=zona.coordinates).order_by('price')
    for alojamiento in alojamientos:
        costo = alojamiento.price * dias * cantidad_personas
        if agregar(alojamiento, desde, costo, "alojamiento"):
            break

    restaurantes = Place.objects.filter(coordinates__within=zona.coordinates, type="restaurant").order_by('average_price')
    comidas_agregadas = 0
    for restaurante in restaurantes:
        if restaurante.average_price is None:
            continue
        costo = restaurante.average_price * cantidad_personas
        fecha_comida = desde + timedelta(days=comidas_agregadas)
        if agregar(restaurante, fecha_comida, costo, "comida"):
            comidas_agregadas += 1
        if comidas_agregadas >= dias:
            break

    actividades = ActivityService.objects.filter(place_id__coordinates__within=zona.coordinates).order_by('price')
    for actividad in actividades:
        fecha = getattr(actividad, 'start_date', desde)
        costo = actividad.price * cantidad_personas
        agregar(actividad, fecha, costo, "actividad")

    eventos = Event.objects.filter(place_id__coordinates__within=zona.coordinates, start_date__range=(desde, hasta)).order_by('price')
    for evento in eventos:
        costo = evento.price * cantidad_personas
        agregar(evento, evento.start_date, costo, "evento")

    return items