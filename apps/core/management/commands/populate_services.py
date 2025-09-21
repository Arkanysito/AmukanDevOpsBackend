import random
from datetime import datetime, timedelta, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.experiences.models import TransportService, AccommodationService, ActivityService, Event
from apps.organizations.models import Organization, OrganizationUser
from apps.location.models import Place
from apps.users.models import CustomUser
from apps.core.constants import (
    AccommodationType, ActivityType, Currency, TransportType,
    OrganizationUserRole, SubscriptionPlan, OrganizationCategory
)

class Command(BaseCommand):
    help = "Pobla datos ficticios en Organization, OrganizationUser y servicios"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Iniciando población de datos..."))

        # Crear usuarios si no existen
        users = list(CustomUser.objects.all())
        if not users:
            for i in range(3):
                user = CustomUser.objects.create_user(
                    username=f"user{i}",
                    email=f"user{i}@example.com",
                    password="test1234"
                )
                users.append(user)

        # Crear organizaciones
        organizations = []
        for i in range(5):
            org = Organization.objects.create(
                name=f"Organización {i}",
                email=f"org{i}@example.com",
                category=random.choice([c[0] for c in OrganizationCategory.choices]),
                subscription_plan=random.choice([s[0] for s in SubscriptionPlan.choices]),
                contact_info={"phone": f"+56 9 1234 567{i}", "website": f"https://org{i}.cl"},
                rating=round(random.uniform(3.0, 5.0), 1)
            )
            OrganizationUser.objects.create(
                organization_id=org,
                user_id=random.choice(users),
                role=random.choice([r[0] for r in OrganizationUserRole.choices])
            )
            organizations.append(org)

        # Verificar lugares
        places = list(Place.objects.all())
        if not places:
            self.stdout.write(self.style.WARNING("No hay lugares disponibles en Place. Se requieren para poblar servicios."))
            return

        # Poblar TransportService
        for i in range(10):
            TransportService.objects.create(
                organization_id=random.choice(organizations),
                place_id=random.choice(places),
                name=f"Transporte {i}",
                description="Servicio de transporte local",
                price=random.uniform(10, 100),
                price_currency=Currency.CLP,
                transport_type=random.choice([t[0] for t in TransportType.choices]),
                schedule={"lunes": "08:00-18:00", "viernes": "08:00-20:00"},
                capacity=random.randint(10, 50),
                rating=round(random.uniform(3.0, 5.0), 1)
            )

        # Poblar AccommodationService
        for i in range(10):
            AccommodationService.objects.create(
                organization_id=random.choice(organizations),
                place_id=random.choice(places),
                name=f"Alojamiento {i}",
                description="Hospedaje cómodo y céntrico",
                price=random.uniform(50, 300),
                price_currency=Currency.CLP,
                accommodation_type=random.choice([a[0] for a in AccommodationType.choices]),
                amenities={"wifi": True, "desayuno": True},
                beds=random.randint(1, 4),
                room_capacity=random.randint(1, 6),
                check_in_time=time(14, 0),
                check_out_time=time(11, 0),
                parking=random.choice([True, False]),
                rating=round(random.uniform(3.5, 5.0), 1)
            )

        # Poblar ActivityService
        for i in range(10):
            ActivityService.objects.create(
                organization_id=random.choice(organizations),
                place_id=random.choice(places),
                name=f"Actividad {i}",
                description="Actividad recreativa al aire libre",
                price=random.uniform(20, 150),
                price_currency=Currency.CLP,
                activity_type=random.choice([a[0] for a in ActivityType.choices]),
                duration_minutes=random.randint(30, 180),
                guide_included=random.choice([True, False]),
                details={"nivel": "intermedio"},
                rating=round(random.uniform(2.5, 5.0), 1)
            )

        # Poblar Event
        for i in range(20):
            start = timezone.now() + timedelta(days=random.randint(1, 30))
            end = start + timedelta(hours=random.randint(2, 6))
            Event.objects.create(
                organization_id=random.choice(organizations),
                place_id=random.choice(places),
                name=f"Evento {i}",
                description="Evento cultural destacado",
                start_date=start,
                end_date=end,
                price=random.uniform(0, 100),
                price_currency=Currency.CLP,
                details={"categoría": "cultural"},
                is_featured=random.choice([True, False]),
                rating=round(random.uniform(3.0, 5.0), 1)
            )

        self.stdout.write(self.style.SUCCESS("¡Datos poblados exitosamente!"))