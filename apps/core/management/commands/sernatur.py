import requests
from bs4 import BeautifulSoup
import json
import time as time_module
import random
from datetime import datetime, timedelta, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.experiences.models import AccommodationService, ActivityService, Event
from apps.organizations.models import Organization, OrganizationUser
from apps.location.models import Place
from apps.users.models import CustomUser
from apps.core.constants import (
    AccommodationType, ActivityType, Currency, TransportType,
    OrganizationUserRole, SubscriptionPlan, OrganizationCategory
)

class SernaturScraper:
    def __init__(self):
        self.base_url = "https://serviciosturisticos.sernatur.cl"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def get_total_pages(self, tipo_servicio):
        """Obtiene el número total de páginas para un tipo de servicio"""
        url = f"{self.base_url}/nueva_busqueda.php?page=1&tipo_servicio={tipo_servicio}&clase_servicio=0&region=0&comuna=0&nombre="
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Buscar la paginación - según la estructura HTML proporcionada
            pagination = soup.find('div', id='paginacion')
            if pagination:
                pages = pagination.find_all('li', class_='numeracion')
                if pages:
                    # El último elemento numérico es el total de páginas
                    last_page = pages[-1].text.strip()
                    return int(last_page) if last_page.isdigit() else 1
            return 1
        except Exception as e:
            print(f"Error obteniendo páginas para tipo {tipo_servicio}: {e}")
            return 1

    def scrape_services(self, tipo_servicio, servicio_nombre):
        """Scrapea todos los servicios de un tipo específico"""
        all_services = []
        total_pages = self.get_total_pages(tipo_servicio)
        
        print(f"Scrapeando {servicio_nombre} - {total_pages} páginas")
        
        for page in range(1, total_pages + 1):
            print(f"Página {page} de {total_pages}")
            
            url = f"{self.base_url}/nueva_busqueda.php?page={page}&tipo_servicio={tipo_servicio}&clase_servicio=0&region=0&comuna=0&nombre="
            
            try:
                response = self.session.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Encontrar los contenedores de servicios - según la estructura HTML
                service_containers = soup.find_all('div', class_='main_caja')
                
                for container in service_containers:
                    service_data = self.extract_service_data(container, tipo_servicio)
                    if service_data:
                        all_services.append(service_data)
                
                time_module.sleep(1)  # Espera entre páginas
                
            except Exception as e:
                print(f"Error en página {page}: {e}")
                continue
        
        return all_services

    def extract_service_data(self, container, tipo_servicio):
        """Extrae los datos de un servicio individual según la estructura HTML real"""
        try:
            # Nombre del servicio
            name_elem = container.find('a', class_='nombre')
            name = name_elem.text.strip() if name_elem else "Sin nombre"
            
            # Dirección para usar como descripción
            address_elem = container.find('p', string=lambda text: text and 'fas fa-map-marker' in str(text))
            description = ""
            if address_elem:
                address_text = address_elem.get_text(strip=True)
                description = address_text
            
            # Información de contacto
            contact_info = {}
            
            # Teléfono
            phone_elem = container.find('p', string=lambda text: text and 'fas fa-phone' in str(text))
            if phone_elem:
                phone_text = phone_elem.get_text(strip=True)
                contact_info['phone'] = phone_text.replace('(56)', '').strip()
            
            # Región
            region_elem = container.find('p', string=lambda text: text and 'fas fa-location-arrow' in str(text))
            region = "Sin región"
            if region_elem:
                region_text = region_elem.get_text(strip=True)
                region = region_text.strip()
            
            # Tipo de alojamiento específico
            accommodation_type = "Hotel"  # Por defecto
            type_elems = container.find_all('p')
            for elem in type_elems:
                text = elem.get_text(strip=True)
                if 'Hotel' in text and len(text) < 50:  # Evitar textos largos que son direcciones
                    accommodation_type = "Hotel"
                    break
                elif 'Cabañas' in text:
                    accommodation_type = "Cabañas"
                    break
                elif 'Camping' in text:
                    accommodation_type = "Camping"
                    break
                elif 'Hostal' in text:
                    accommodation_type = "Hostal"
                    break
                elif 'Hostería' in text:
                    accommodation_type = "Hostería"
                    break
                elif 'Apart-Hotel' in text:
                    accommodation_type = "Apart-Hotel"
                    break
            
            # Estado de registro (usaremos esto para determinar si está activo)
            is_active = True
            registration_elem = container.find('div', class_='servicio-no-cumple-inspeccion')
            if registration_elem:
                is_active = False
            
            # Imagen
            image_elem = container.find('img')
            image_url = ""
            if image_elem and image_elem.get('src'):
                image_url = self.base_url + image_elem['src'] if image_elem['src'].startswith('/') else image_elem['src']
            
            # Tipo específico basado en el parámetro
            service_type = self.map_service_type(tipo_servicio)
            
            return {
                'name': name,
                'description': description or f"Servicio de {accommodation_type} en {region}",
                'region': region,
                'contact_info': contact_info,
                'service_type': service_type,
                'original_type': tipo_servicio,
                'accommodation_type': accommodation_type,
                'is_active': is_active,
                'image_url': image_url,
                'address': description
            }
            
        except Exception as e:
            print(f"Error extrayendo datos: {e}")
            return None

    def map_service_type(self, tipo_servicio):
        """Mapea los tipos de servicio de SERNATUR a los modelos internos"""
        type_mapping = {
            '1': 'alojamiento',
            '2': 'alimentacion', 
            '3': 'transporte',
            '4': 'recreacion',
            '5': 'eventos',
            '10': 'transporte',
            '16': 'recreacion',
            '12': 'recreacion',
            '14': 'recreacion',
            '15': 'recreacion',
            '22': 'recreacion',
            '17': 'recreacion',
            '18': 'recreacion',
            '8': 'transporte',
            '6': 'transporte',
            '5': 'transporte',
            '19': 'transporte',
            '13': 'recreacion'
        }
        return type_mapping.get(str(tipo_servicio), 'otros')

    def map_accommodation_type(self, sernatur_type):
        """Mapea los tipos de alojamiento de SERNATUR a los modelos internos"""
        type_mapping = {
            'Hotel': AccommodationType.HOTEL,
            'Cabañas': AccommodationType.CABIN,
            'Camping': AccommodationType.CAMPING,
            'Hostal': AccommodationType.HOSTEL,
            'Hostería': AccommodationType.INN,
            'Apart-Hotel': AccommodationType.APARTMENT,
            'Bed and Breakfast': AccommodationType.BED_BREAKFAST,
            'Residencial': AccommodationType.GUESTHOUSE,
            'Termas': AccommodationType.SPA
        }
        return type_mapping.get(sernatur_type, AccommodationType.HOTEL)

    def get_all_services(self):
        """Obtiene todos los tipos de servicios"""
        all_services = []
        
        # Tipos de servicio en SERNATUR (solo los principales para evitar muchos requests)
        service_types = [
            ('1', 'Alojamiento turístico'),
            ('3', 'Transporte'),
            # ('2', 'Alimentación'),  # Comentado para reducir tiempo
            # ('4', 'Recreación'),    # Comentado para reducir tiempo  
            # ('5', 'Eventos')        # Comentado para reducir tiempo
        ]
        
        for tipo_id, tipo_nombre in service_types:
            services = self.scrape_services(tipo_id, tipo_nombre)
            all_services.extend(services)
            print(f"Obtenidos {len(services)} servicios de {tipo_nombre}")
            time_module.sleep(2)
        
        return all_services

class Command(BaseCommand):
    help = "Pobla datos reales desde SERNATUR Chile"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--max-services',
            type=int,
            default=20,
            help='Número máximo de servicios a importar (por defecto: 20)'
        )
        parser.add_argument(
            '--skip-scraping',
            action='store_true',
            help='Usar datos de ejemplo sin hacer scraping real'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Iniciando scraping de datos reales desde SERNATUR..."))

        max_services = options['max_services']
        skip_scraping = options['skip_scraping']

        if skip_scraping:
            real_services = self.get_sample_data()
            self.stdout.write(self.style.WARNING("Usando datos de ejemplo..."))
        else:
            scraper = SernaturScraper()
            self.stdout.write(self.style.SUCCESS("Iniciando scraping de SERNATUR..."))
            real_services = scraper.get_all_services()
        
        self.stdout.write(self.style.SUCCESS(f"Se obtuvieron {len(real_services)} servicios"))
        
        if len(real_services) > max_services:
            real_services = real_services[:max_services]
            self.stdout.write(self.style.WARNING(f"Limitando a {max_services} servicios"))

        # Crear usuarios base si no existen
        users = self.create_base_users()
        
        # Crear organizaciones
        organizations = self.create_organizations(real_services, users)
        
        # Obtener lugares disponibles
        places = list(Place.objects.all())
        if not places:
            self.stdout.write(self.style.ERROR("No hay lugares disponibles. Creando lugar por defecto..."))
            place = Place.objects.create(
                name="Lugar por defecto",
                latitude=-33.4489,
                longitude=-70.6693,
                address="Santiago, Chile"
            )
            places = [place]

        # Poblar servicios
        self.populate_real_services(real_services, organizations, places, scraper)

        self.stdout.write(self.style.SUCCESS("¡Datos reales poblados exitosamente!"))

    def create_base_users(self):
        """Crea usuarios base si no existen"""
        users = list(CustomUser.objects.all())
        if not users:
            self.stdout.write(self.style.WARNING("Creando usuarios base..."))
            for i in range(2):
                user = CustomUser.objects.create_user(
                    username=f"org_user_{i}",
                    email=f"org{i}@sernatur.cl",
                    password="test1234"
                )
                users.append(user)
        return users

    def create_organizations(self, real_services, users):
        """Crea organizaciones basadas en los servicios reales"""
        organizations = []
        used_names = set()
        
        num_organizations = min(3, len(real_services))
        
        for i in range(num_organizations):
            service = real_services[i]
            org_name = f"Org. {service['name'][:15]}"
            
            base_name = org_name
            counter = 1
            while org_name in used_names:
                org_name = f"{base_name} ({counter})"
                counter += 1
            
            used_names.add(org_name)
            
            org = Organization.objects.create(
                name=org_name,
                email=f"org{i}@sernatur.cl",
                category=OrganizationCategory.TOURISM,
                subscription_plan=SubscriptionPlan.BASIC,
                contact_info=service['contact_info'],
                rating=round(random.uniform(3.0, 5.0), 1)
            )
            
            OrganizationUser.objects.create(
                organization_id=org,
                user_id=random.choice(users),
                role=OrganizationUserRole.ADMIN
            )
            
            organizations.append(org)
            self.stdout.write(self.style.SUCCESS(f"Organización creada: {org.name}"))
        
        return organizations

    def populate_real_services(self, real_services, organizations, places, scraper):
        """Pobla la base de datos con servicios reales - SOLO CAMPOS EXISTENTES"""
        transport_count = 0
        accommodation_count = 0
        activity_count = 0
        event_count = 0

        for service in real_services:
            org = random.choice(organizations)
            place = random.choice(places)
            
            try:
                if service['service_type'] == 'alojamiento':
                    accommodation_type = scraper.map_accommodation_type(service.get('accommodation_type', 'Hotel'))
                    
                    # SOLO USAR CAMPOS QUE EXISTEN EN EL MODELO
                    AccommodationService.objects.create(
                        organization_id=org,
                        place_id=place,
                        name=service['name'][:100],
                        description=service['description'][:500] or f"Servicio de alojamiento en {service['region']}",
                        price=round(random.uniform(50, 300), 2),
                        price_currency=Currency.CLP,
                        accommodation_type=accommodation_type,
                        amenities={
                            "wifi": random.choice([True, False]),
                            "desayuno": random.choice([True, False]),
                            "estacionamiento": random.choice([True, False])
                        },
                        beds=random.randint(1, 4),
                        capacity=random.randint(1, 6),
                        check_in_time=time(14, 0),
                        check_out_time=time(11, 0),
                        parking=random.choice([True, False]),
                        rating=round(random.uniform(3.5, 5.0), 1)
                        # REMOVIDO: additional_info - no existe en el modelo
                    )
                    accommodation_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Creado alojamiento: {service['name'][:30]}"))

                elif service['service_type'] in ['recreacion', 'alimentacion']:
                    ActivityService.objects.create(
                        organization_id=org,
                        place_id=place,
                        name=service['name'][:100],
                        description=service['description'][:500] or f"Servicio de actividades en {service['region']}",
                        price=round(random.uniform(20, 150), 2),
                        price_currency=Currency.CLP,
                        activity_type=random.choice([a[0] for a in ActivityType.choices]),
                        duration_minutes=random.randint(30, 180),
                        guide_included=random.choice([True, False]),
                        details={"nivel": "intermedio", "region": service['region']},
                        rating=round(random.uniform(2.5, 5.0), 1)
                    )
                    activity_count += 1

                elif service['service_type'] == 'eventos':
                    start = timezone.now() + timedelta(days=random.randint(1, 30))
                    end = start + timedelta(hours=random.randint(2, 6))
                    Event.objects.create(
                        organization_id=org,
                        place_id=place,
                        name=service['name'][:100],
                        description=service['description'][:500] or f"Evento en {service['region']}",
                        start_date=start,
                        end_date=end,
                        price=round(random.uniform(0, 100), 2),
                        price_currency=Currency.CLP,
                        details={"categoría": "cultural", "region": service['region']},
                        is_featured=random.choice([True, False]),
                        rating=round(random.uniform(3.0, 5.0), 1)
                    )
                    event_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error creando servicio {service['name']}: {e}"))
                continue

        self.stdout.write(self.style.SUCCESS(
            f"Resumen de servicios creados:\n"
            f"  - Transporte: {transport_count}\n"
            f"  - Alojamiento: {accommodation_count}\n"
            f"  - Actividades: {activity_count}\n"
            f"  - Eventos: {event_count}\n"
            f"Total: {transport_count + accommodation_count + activity_count + event_count}"
        ))

    def get_sample_data(self):
        """Provee datos de ejemplo"""
        return [
            {
                'name': 'Hotel Ejemplo Santiago',
                'description': 'Av. Principal 123, Santiago',
                'region': 'Región Metropolitana',
                'contact_info': {'phone': '+56 2 1234 5678'},
                'service_type': 'alojamiento',
                'accommodation_type': 'Hotel'
            },
            {
                'name': 'Bus Turístico Valparaíso', 
                'description': 'Recorrido por cerros de Valparaíso',
                'region': 'Región de Valparaíso',
                'contact_info': {'phone': '+56 32 9876 5432'},
                'service_type': 'transporte'
            }
        ]