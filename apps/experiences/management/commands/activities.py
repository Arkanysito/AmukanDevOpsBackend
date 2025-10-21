from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from apps.experiences.models import ActivityService, ActivityType
from apps.organizations.models import Organization
from apps.location.models import Place, PlaceType
from apps.core.constants import OrganizationCategory, SubscriptionPlan, Currency
import random

ACTIVIDADES = [
    {
        "nombre": "BALTAZAR",
        "direccion": "Arlegui 610, Local 7",
        "coords": (-71.553543, -33.023889),
        "hora": "Lunes a viernes 11:00 a 14:30 hrs",
        "detalles": "Atención presencial y virtual. Teléfono: 32-2264300. Idiomas: Guías Bilingües. Servicios: City tour Viña del Mar, Valparaíso, Isla Negra, Santiago. Traslado al aeropuerto. Correos: contacto@baltazar.cl, ventas@baltazar.cl. Web: www.baltazar.cl."
    },
    {
        "nombre": "BOHEMIA TOUR",
        "direccion": "Esmeralda 1074 Oficina 1006, Valparaíso",
        "coords": (-71.624985, -33.042137),
        "hora": None,
        "detalles": "Teléfono: +56 9 9433 7575. Servicios: City tour Viña del Mar, Valparaíso, traslados, viñedos, Zapallar e Isla Negra. Idiomas: Guías bilingües (francés con aviso previo). Correo: info@bohemiatour.cl. Web: www.bohemiatour.cl. Instagram: @bohemiatour."
    },
    {
        "nombre": "EXTREMO NORTE",
        "direccion": "Av. Lusitania 554, Viña del Mar",
        "coords": (-71.529336, -33.026718),
        "hora": "Previa reserva",
        "detalles": "Teléfono: +56 9 9844 3711. Servicios: City tour de cultura y naturaleza en Valparaíso y alrededores. Idiomas: Inglés. Correo: reservas@extremonorte.cl. Web: www.extremonorte.cl. Instagram: @extremonorte_chile."
    },
    {
        "nombre": "FARITOUR",
        "direccion": "Amunátegui 2056, Recreo, Viña del Mar",
        "coords": (-71.584405, -33.028942),
        "hora": None,
        "detalles": "Teléfonos: +56 9 9020 6410 / +56 9 9330 7990. Servicios: City tour Viña del Mar, Valparaíso, Santiago, Isla Negra, Ruta del Vino, Zapallar. Idiomas: Inglés. Correo: transportesyturismofaritour@gmail.com. Web: www.faritour.cl."
    },
    {
        "nombre": "FRANCO TOUR",
        "direccion": "Atención virtual",
        "coords": (-71.5519, -33.0245),
        "hora": None,
        "detalles": "Teléfono: +56 9 9943 3039. Servicios: City tour Valparaíso, Viña del Mar, Isla Negra, Ruta del Vino, Caminatas. Idiomas: Inglés y español. Correo: francotours@hotmail.com. Instagram: @francotours. Facebook: @franco.tours."
    },
    {
        "nombre": "KELTEWE",
        "direccion": "7 oriente 379 Departamento 403",
        "coords": (-71.544132, -33.023146),
        "hora": None,
        "detalles": "Atención solo virtual. Teléfono: 9-82173955. Servicios: City tour Patrimonial, Casablanca, Quillota, Beer Tour, Tour del Vino, foodie tour. Idiomas: Inglés. Correo: info@keltewe.cl. Web: www.keltewe.cl."
    },
    {
        "nombre": "SAILING & TOURS",
        "direccion": "Arlegui 263, Oficina 601, Viña del Mar",
        "coords": (-71.558670, -33.022591),
        "hora": None,
        "detalles": "Atención presencial y virtual. Teléfono: +56 9 7160 8611. Idiomas: Inglés. Facebook: LyS Sailing Tours. Correo: info@lysailingtours.cl. Web: www.lysailingtours.cl. Servicios: Travesías en veleros, City tours."
    },
    {
        "nombre": "TURISMO LAGO PEHOE",
        "direccion": "Capitán Larraguibel 456",
        "coords": (-71.512748, -33.008260),
        "hora": None,
        "detalles": "Teléfono: +56 9 7767 2031. Idiomas: Inglés, portugués. Servicios: City tours Viña del Mar, Valparaíso, Viñedos de Casablanca, Isla Negra. Transporte a turistas. Correo: lagopehoetours@gmail.com. Web: www.lagopehoetours.cl."
    },
    {
        "nombre": "VIÑA DE LA MAR",
        "direccion": "Calle Valparaíso 1055, zócalo",
        "coords": (-71.547021, -33.025459),
        "hora": None,
        "detalles": "Teléfono: +56 9 6390 3575. Idiomas: Inglés. Servicios: City tour a Valparaíso, Viña del Mar, Reñaca, Concón, Viñedos, Isla Negra, Santiago, recitales, paseos de curso, traslados al aeropuerto, nieve y alojamientos. Correo: gpendolo@gmail.com."
    },
    {
        "nombre": "TURISMO VALPARAÍSO DEL MAR",
        "direccion": "Calle Valparaíso 1055, Oficina 4 zócalo",
        "coords": (-71.547021, -33.025459),
        "hora": None,
        "detalles": "Teléfono: +56 9 6833 8409. Idiomas: Inglés, italiano, alemán y francés. Servicios: City tour a Valparaíso, Viña del Mar. Correo: josemrd23@gmail.com. Web: www.transferdelmar.cl."
    },
    {
        "nombre": "VALPO VINA",
        "direccion": "El Bosque 1272, Alto Verde, Placilla, Valparaíso",
        "coords": (-71.640571, -33.454388),
        "hora": None,
        "detalles": "Atención presencial y virtual. Teléfonos: 32-2218669 / +56 9 9258 6147 / +56 9 9536 0430. Idiomas: Inglés, alemán, francés, portugués. Correos: info@valpovinaturismo.cl, ventas1@valpovinaturismo.cl, servicioalcliente@valpovinaturismo.cl. Web: www.valpovinaturismo.cl."
    },
]


class Command(BaseCommand):
    help = "Carga actividades turísticas en la base de datos"

    def handle(self, *args, **options):
        self.stdout.write("🚀 Creando organización base...")
        organizacion, created = Organization.objects.get_or_create(
            name="munivina",
            defaults={
                "email": "municipiodecuidados@munivina.cl",
                "category": OrganizationCategory.PRIVATE,
                "subscription_plan": SubscriptionPlan.FREE,
                "contact_info": {"phone": "+56 9 1234 5678", "website": "https://www.munivina.cl/"},
                "rating": 3,
            }
        )

        if created:
            self.stdout.write("✅ Organización creada.")
        else:
            self.stdout.write("ℹ️ La organización ya existía.")

        for tour in ACTIVIDADES:
            lon, lat = tour["coords"]
            point = Point(lon, lat)

            # Verificar si el lugar ya existe por nombre y coordenadas
            place, place_created = Place.objects.get_or_create(
                organization_id=organizacion,
                name=tour["nombre"],
                coordinates=point,
                defaults={
                    "description": tour["detalles"],
                    "address": tour["direccion"],
                    "type": random.choice([choice[0] for choice in PlaceType.choices]),
                    "schedule": {"horario": tour["hora"]} if tour["hora"] else None,
                }
            )

            if place_created:
                self.stdout.write(f"📍 Lugar '{tour['nombre']}' creado con coordenadas {tour['coords']}")
            else:
                self.stdout.write(f"ℹ️ Lugar '{tour['nombre']}' ya existía, se reutiliza")

            # Verificar si la actividad ya existe
            activity, activity_created = ActivityService.objects.get_or_create(
                organization_id=organizacion,
                name=tour["nombre"],
                defaults={
                    "activity_type": ActivityType.WALKING_TOUR,
                    "duration_minutes": 90,
                    "guide_included": True,
                    "details": {"detalles": tour["detalles"]},
                    "price": 0,
                    "price_currency": Currency.CLP,
                    "place_id": place,
                }
            )

            if activity_created:
                self.stdout.write(f"🌍 Actividad '{tour['nombre']}' creada y asignada al lugar")
            else:
                # Si la actividad ya existía, también actualizamos el lugar por si acaso
                activity.place_id = place
                activity.save()
                self.stdout.write(f"ℹ️ Actividad '{tour['nombre']}' ya existía, se actualizó el lugar")

        self.stdout.write(self.style.SUCCESS("✅ Proceso de carga de actividades completado."))