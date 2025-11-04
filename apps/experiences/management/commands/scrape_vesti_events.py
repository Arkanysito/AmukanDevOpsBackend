import re
import time
import random
import unicodedata
from datetime import datetime

import requests
import urllib.parse
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.gis.geos import Point
from django.db.models import Q
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

from apps.experiences.models import Event
from apps.organizations.models import Organization
from apps.location.models import Place, Zone
from apps.core.constants import OrganizationCategory, SubscriptionPlan, Currency, PlaceType


class Command(BaseCommand):
    help = 'Scrapes events from Vesti.cl website and saves them to the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--city',
            type=str,
            default='viña del mar',
            help='City to search events for (default: viña del mar)'
        )
        parser.add_argument(
            '--year',
            type=int,
            default=2025,
            help='Year for the events (default: 2025)'
        )
        parser.add_argument(
            '--use-system-chrome',
            action='store_true',
            default=True,
            help='Use system Chrome instead of downloading'
        )

    def handle(self, *args, **options):
        city = options['city']
        year = options['year']
        use_system_chrome = options['use_system_chrome']
        
        self.stdout.write(f"🚀 Starting Vesti events scraper for {city}...")
        
        try:
            self.scrape_vesti_events(city, year, use_system_chrome)
            self.stdout.write(
                self.style.SUCCESS('✅ Successfully completed Vesti events scraping!')
            )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'❌ Error during scraping: {str(e)}')
            )
            raise

    def setup_driver(self, use_system_chrome=True):
        """Configura el driver de Selenium usando Chrome del sistema"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
        # Para evitar detección como bot
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        try:
            if use_system_chrome:
                # Usar Chrome del sistema que ya está instalado
                self.stdout.write("🔧 Using system Chrome...")
                # Especificar la ruta del ejecutable de Chrome
                options.binary_location = "/usr/bin/google-chrome-stable"
                
                # Usar ChromeDriverManager para obtener el driver compatible
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            else:
                # Descargar Chrome (fallback)
                self.stdout.write("🔧 Downloading Chrome via webdriver-manager...")
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            
            # Ejecutar script para evitar detección
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Error setting up Chrome driver: {e}")
            )
            # Intentar método alternativo sin webdriver-manager
            self.stdout.write("🔄 Trying alternative Chrome setup...")
            try:
                # Intentar usar chromedriver directamente si está disponible
                service = Service('/usr/bin/chromedriver')  # Ruta común en sistemas Linux
                driver = webdriver.Chrome(service=service, options=options)
                return driver
            except:
                # Último intento: usar el ejecutable de Chrome directamente
                self.stdout.write("🔄 Using direct Chrome executable...")
                options.binary_location = "/usr/bin/google-chrome-stable"
                driver = webdriver.Chrome(options=options)
                return driver

    def estandarizar_evento(self, texto):
        """Convierte texto de evento a formato slug estandarizado"""
        if not texto:
            return ""
            
        # quitar "Evento:" al inicio (insensible a mayúsculas)
        texto = re.sub(r'^\s*evento:\s*', '', texto, flags=re.I).strip().lower()

        # normalizar: ñ->n y quitar tildes
        texto = texto.replace('ñ', 'n')
        texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')

        # quedarnos solo con grupos alfanuméricos y unir con guiones
        tokens = re.findall(r'[a-z0-9]+', texto)
        slug = '-'.join(tokens)

        return slug

    def normalizar_texto(self, texto):
        """Convierte texto a minúsculas sin tildes ni caracteres especiales"""
        if not texto:
            return ""
        texto = texto.lower()
        texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
        return texto

    def extract_price_from_container(self, container):
        """Extrae el precio del contenedor del evento en la página de búsqueda"""
        try:
            # Buscar el span que contiene el precio
            price_span = container.find('span', class_='text-default-700 text-sm')
            if price_span:
                price_text = price_span.get_text(strip=True)
                self.stdout.write(f"💰 Price text found: {price_text}")
                
                # Extraer el número del precio (formato chileno: "Desde $0", "$5.000", "$10.000", etc.)
                price_match = re.search(r'[\$]?\s*(\d+[.,]?\d*)', price_text)
                if price_match:
                    price_str = price_match.group(1)
                    
                    # En formato chileno, el punto separa miles, no decimales
                    # Remover puntos (separadores de miles) y convertir a float
                    price_str = price_str.replace('.', '').replace(',', '.')
                    price = float(price_str)
                    self.stdout.write(f"💰 Extracted price: ${price:,.0f}")  # Formatear con separadores de miles
                    return price
                
                # Si no encuentra número, podría ser "Gratis" o "Entrada liberada"
                if any(word in price_text.lower() for word in ['gratis', 'liberada', 'free', '0']):
                    self.stdout.write("💰 Price: Gratis")
                    return 0
                
            return 0
        except Exception as e:
            self.stdout.write(f"⚠️ Error extracting price: {e}")
            return 0

    def extract_event_data_from_container(self, container):
        """Extrae todos los datos del evento desde el contenedor en la página de búsqueda"""
        try:
            # Extraer nombre del lugar/organizador
            vendor_name_tag = container.find('h2', class_='text-small font-medium text-default-700 line-clamp-1')
            vendor_name = vendor_name_tag.get_text(strip=True) if vendor_name_tag else None
            
            # Extraer nombre del evento
            event_name_tag = container.find('h2', class_='text-small font-medium line-clamp-2')
            event_name = event_name_tag.get_text(strip=True) if event_name_tag else None
            
            # Extraer fecha
            date_tag = container.find('p', class_='text-small text-default-700')
            date_text = date_tag.get_text(strip=True) if date_tag else None
            
            # Extraer precio
            price = self.extract_price_from_container(container)
            
            # Extraer imagen
            img_tag = container.find('img')
            image_url = img_tag.get('src') if img_tag else None
            
            # Crear slug para la URL
            slug = self.estandarizar_evento(event_name) if event_name else None
            
            return {
                'vendor_name': vendor_name,
                'event_name': event_name,
                'date_text': date_text,
                'price': price,
                'image_url': image_url,
                'slug': slug
            }
            
        except Exception as e:
            self.stdout.write(f"⚠️ Error extracting event data from container: {e}")
            return None

    def find_existing_place(self, place_name, address):
        """Busca un lugar existente en la base de datos por nombre o dirección"""
        try:
            # Normalizar nombres para búsqueda
            normalized_name = self.normalizar_texto(place_name)
            
            # Buscar por nombre (búsqueda flexible)
            places = Place.objects.filter(
                Q(name__icontains=place_name) |
                Q(name__icontains=normalized_name) |
                Q(address__icontains=place_name) |
                Q(address__icontains=address)
            ).distinct()
            
            if places.exists():
                # Si hay múltiples resultados, intentar encontrar el más preciso
                exact_match = places.filter(name__iexact=place_name).first()
                if exact_match:
                    return exact_match
                
                # Buscar por dirección si está disponible
                if address:
                    address_match = places.filter(address__icontains=address).first()
                    if address_match:
                        return address_match
                
                # Devolver el primer resultado
                return places.first()
            
            return None
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Error searching for existing place: {e}")
            )
            return None

    def get_default_coordinates_for_city(self, city):
        """Devuelve coordenadas por defecto para la ciudad"""
        city_coordinates = {
            'viña del mar': Point(-71.5517, -33.0245),  # Coordenadas aproximadas de Viña del Mar
            'valparaíso': Point(-71.6200, -33.0458),    # Coordenadas aproximadas de Valparaíso
            'santiago': Point(-70.6693, -33.4489),      # Coordenadas aproximadas de Santiago
        }
        
        normalized_city = self.normalizar_texto(city)
        for city_key, coords in city_coordinates.items():
            if city_key in normalized_city:
                return coords
        
        # Coordenadas por defecto de Viña del Mar
        return Point(-71.5517, -33.0245)

    def get_or_create_place(self, place_name, address, org_vesti, zone):
        """Obtiene un lugar existente o crea uno nuevo si no existe"""
        # Primero buscar si el lugar ya existe
        existing_place = self.find_existing_place(place_name, address)
        
        if existing_place:
            self.stdout.write(f"📍 Using existing place: {existing_place.name}")
            return existing_place, False
        
        # Si no existe, crear uno nuevo
        try:
            # Obtener coordenadas de la dirección
            lat, lon = self.direccion_a_coordenadas_nominatim(address, place_name)
            
            # Si no se pudieron obtener coordenadas, usar coordenadas por defecto de la ciudad
            if not lat or not lon:
                self.stdout.write(f"⚠️ Could not geocode address, using default coordinates for city")
                coordinates = self.get_default_coordinates_for_city(address)
            else:
                coordinates = Point(lon, lat)  # Note: Point uses (x, y) = (longitude, latitude)
            
            # Determinar el tipo de lugar basado en el nombre
            place_type = self.determine_place_type(place_name)
            
            place = Place.objects.create(
                name=place_name[:100],
                organization_id=org_vesti,
                zone_id=zone,
                address=address,
                type=place_type,
                coordinates=coordinates,
                average_price=None,  # No tenemos esta información del scraping
                rating=round(random.uniform(3.0, 5.0), 1)
            )
            
            self.stdout.write(f"📍 Created new place: {place.name} ({place_type})")
            return place, True
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error creating place {place_name}: {e}")
            )
            return None, False

    def determine_place_type(self, place_name):
        """Determina el tipo de lugar basado en el nombre"""
        place_name_lower = place_name.lower()
        
        # Mapeo de palabras clave a tipos de lugar
        type_mapping = {
            'bar': PlaceType.BAR,
            'pub': PlaceType.PUB,
            'club': PlaceType.NIGHTCLUB,
            'discotheque': PlaceType.NIGHTCLUB,
            'discoteca': PlaceType.NIGHTCLUB,
            'nightclub': PlaceType.NIGHTCLUB,
            'restaurant': PlaceType.RESTAURANT,
            'restaurante': PlaceType.RESTAURANT,
            'cafe': PlaceType.CAFE,
            'café': PlaceType.CAFE,
            'hotel': PlaceType.HOTEL,
            'teatro': PlaceType.THEATRE,
            'theatre': PlaceType.THEATRE,
            'cinema': PlaceType.CINEMA,
            'cine': PlaceType.CINEMA,
            'stadium': PlaceType.STADIUM,
            'estadio': PlaceType.STADIUM,
            'arena': PlaceType.STADIUM,
            'concierto': PlaceType.CONCERT_HALL,
            'concert': PlaceType.CONCERT_HALL,
            'auditorio': PlaceType.CONCERT_HALL,
            'sporting': PlaceType.STADIUM,
            'plaza': PlaceType.PARK,
            'park': PlaceType.PARK,
            'parque': PlaceType.PARK,
            'psiquis': PlaceType.BAR,
            'hollywood': PlaceType.NIGHTCLUB,
            'alcazaba': PlaceType.BAR,
            'sanguchela': PlaceType.RESTAURANT,
        }
        
        # Buscar palabras clave en el nombre del lugar
        for keyword, place_type in type_mapping.items():
            if keyword in place_name_lower:
                return place_type
        
        # Por defecto, usar BAR para eventos nocturnos
        return PlaceType.BAR

    def direccion_a_coordenadas_nominatim(self, direccion, lugar):
        """Convierte una dirección en (latitud, longitud) usando la API de Nominatim."""
        try:
            if not direccion:
                return None, None
                
            # Codificar la dirección para URL
            direccion_codificada = urllib.parse.quote(direccion)
            
            # Endpoint de Nominatim
            url = f"https://nominatim.openstreetmap.org/search?q={direccion_codificada}&format=json&limit=1"
            
            # Buenas prácticas: incluir un user-agent identificable
            headers = {"User-Agent": "vesti-event-scraper/1.0"}
            
            # Realizar la petición
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()
            
            if not data:
                lugar_codificada = urllib.parse.quote(lugar)
                url = f"https://nominatim.openstreetmap.org/search?q={lugar_codificada}&format=json&limit=1"
                response = requests.get(url, headers=headers, timeout=10)
                data = response.json()

            # Evitar rate limit (1 req/seg recomendado por Nominatim)
            time.sleep(1)
            
            # Extraer coordenadas si hay resultado
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                return lat, lon
            else:
                return None, None
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Error al geocodificar '{direccion}': {e}")
            )
            return None, None

    def formatear_fecha(self, fecha_str, year=2025):
        """
        Convierte una fecha tipo 'sábado 05 abril 20:00' en un objeto datetime.
        Asume el año 2025 por defecto.
        Devuelve un objeto timezone-aware compatible con Django.
        """
        if not fecha_str:
            return timezone.now() + timezone.timedelta(days=random.randint(1, 30))
            
        try:
            # Normalizar texto (minúsculas y sin tildes)
            fecha_str = fecha_str.lower()
            fecha_str = unicodedata.normalize('NFKD', fecha_str).encode('ascii', 'ignore').decode('utf-8')

            # Mapeo de meses en español
            meses = {
                "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
                "octubre": 10, "noviembre": 11, "diciembre": 12
            }

            # Eliminar día de la semana si existe
            partes = fecha_str.split()
            if len(partes) == 4:
                _, dia, mes, hora = partes
            elif len(partes) == 3:
                dia, mes, hora = partes
            else:
                self.stdout.write(
                    self.style.WARNING(f"⚠️ Formato de fecha inesperado: '{fecha_str}'")
                )
                return timezone.now() + timezone.timedelta(days=random.randint(1, 30))

            # Obtener número de mes
            mes_num = meses.get(mes)
            if not mes_num:
                self.stdout.write(
                    self.style.WARNING(f"⚠️ Mes no reconocido: '{mes}'")
                )
                return timezone.now() + timezone.timedelta(days=random.randint(1, 30))

            # Crear datetime
            dia = int(dia)
            if ':' in hora:
                hora, minuto = map(int, hora.split(":"))
            else:
                hora, minuto = 20, 0  # Hora por defecto
                
            fecha = datetime(year, mes_num, dia, hora, minuto)

            # Convertir a timezone de Django
            return timezone.make_aware(fecha, timezone.get_current_timezone())
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Error formateando fecha '{fecha_str}': {e}")
            )
            return timezone.now() + timezone.timedelta(days=random.randint(1, 30))

    def get_or_create_vesti_organization(self):
        """Obtiene o crea la organización Vesti"""
        try:
            org_vesti, created = Organization.objects.get_or_create(
                name="Vesti",
                defaults={
                    "email": "info@vesti.cl",
                    "category": OrganizationCategory.PRIVATE,
                    "subscription_plan": SubscriptionPlan.FREE,
                    "contact_info": {"phone": "+56 9 1234 5678", "website": "https://vesti.cl"},
                    "rating": round(random.uniform(3.0, 5.0), 1)
                }
            )
            if created:
                self.stdout.write(f"✅ Created organization: {org_vesti.name}")
            else:
                self.stdout.write(f"✅ Using existing organization: {org_vesti.name}")
            
            return org_vesti
        except Exception as e:
            self.stderr.write(f"❌ Error creating organization: {e}")
            raise

    def get_or_create_zone(self, zone_name="Viña del Mar"):
        """Obtiene o crea una zona por defecto"""
        try:
            zone, created = Zone.objects.get_or_create(
                name=zone_name,
                defaults={
                    "description": f"Zona de {zone_name}",
                    "boundaries": None
                }
            )
            if created:
                self.stdout.write(f"📍 Created zone: {zone.name}")
            return zone
        except Exception as e:
            self.stdout.write(f"⚠️ Error creating zone: {e}")
            return None

    def scrape_vesti_events(self, city, year, use_system_chrome=True):
        """Función principal que realiza el scraping de eventos"""
        # Obtener o crear organización Vesti
        org_vesti = self.get_or_create_vesti_organization()
        
        # Obtener o crear zona por defecto
        zone = self.get_or_create_zone(city.title())

        # Configurar Selenium
        driver = self.setup_driver(use_system_chrome)
        
        if not driver:
            self.stderr.write("❌ Could not initialize Chrome driver")
            return

        try:
            search_url = f"https://vesti.cl/events?search={urllib.parse.quote(city)}"
            self.stdout.write(f"🌐 Navigating to: {search_url}")
            driver.get(search_url)
            
            # Esperar más tiempo para que cargue la página
            time.sleep(8)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Buscar los contenedores de eventos
            event_containers = soup.find_all("div", class_="relative flex w-full flex-none md:flex-col gap-3")
            
            self.stdout.write(f"📊 {len(event_containers)} event containers encontrados")

            if not event_containers:
                self.stdout.write(self.style.WARNING("⚠️ No events found. The page structure might have changed."))
                return

            events_data = []
            
            # Extraer datos de cada contenedor de evento
            for container in event_containers:
                event_data = self.extract_event_data_from_container(container)
                if event_data and event_data.get('event_name'):
                    events_data.append(event_data)
                    self.stdout.write(f"🎯 Extracted: {event_data['event_name']} - ${event_data['price']}")

            # Procesar cada evento
            events_created = 0

            for i, event_data in enumerate(events_data):
                if not event_data.get('slug'):
                    continue
                    
                url = f"https://vesti.cl/events/{event_data['slug']}"
                self.stdout.write(f"🔍 Processing ({i+1}/{len(events_data)}): {url}")
                
                try:
                    driver.get(url)
                    
                    # Esperar a que cargue la página
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Esperar un poco más para contenido dinámico
                    time.sleep(3)
                    
                    soup2 = BeautifulSoup(driver.page_source, "html.parser")

                    # Buscar ubicación con diferentes selectores
                    p = soup2.find("p", class_="mt-3 text-md")
                    nombre_lugar = soup2.find("p", class_="text-small text-default-500")
                    
                    if p and nombre_lugar:
                        ubicacion = p.get_text(strip=True, separator=" ")
                        nombre_lugar_text = nombre_lugar.get_text(strip=True, separator=" ")
                        
                        # Normalizamos el texto para comparar sin tildes ni mayúsculas
                        normalized_ubicacion = self.normalizar_texto(ubicacion)
                        normalized_city = self.normalizar_texto(city)
                        
                        if normalized_city in normalized_ubicacion:
                            # Obtener descripción
                            desc_element = soup2.find("p", class_="whitespace-pre-line")
                            descripcion = desc_element.get_text(strip=True, separator=" ") if desc_element else f"Evento en {nombre_lugar_text}"
                            
                            # Usar la fecha de la página de búsqueda, o intentar extraer de la página individual
                            fecha_text = event_data.get('date_text')
                            if not fecha_text:
                                fecha_element = soup2.find("span", class_="text-md dark:text-gray-400")
                                fecha_text = fecha_element.get_text(strip=True, separator=" ") if fecha_element else None
                            
                            fecha_inicio = self.formatear_fecha(fecha_text, year)
                            
                            # Usar el precio extraído de la página de búsqueda
                            precio = event_data.get('price', 0)

                            # Obtener o crear el lugar (usa lugares existentes si están en la BD)
                            place, created = self.get_or_create_place(
                                nombre_lugar_text, 
                                ubicacion, 
                                org_vesti, 
                                zone
                            )
                            
                            if not place:
                                continue

                            # Crear evento usando los campos correctos del modelo
                            event = Event.objects.create(
                                organization_id=org_vesti,
                                place_id=place,
                                name=nombre_lugar_text[:200],
                                description=descripcion[:500],
                                start_date=fecha_inicio,
                                end_date=fecha_inicio,
                                price=precio,
                                price_currency=Currency.CLP,
                                details={
                                    "categoría": "música", 
                                    "fuente": "vesti.cl",
                                    "url_original": url,
                                    "slug": event_data['slug'],
                                    "image_url": event_data.get('image_url')
                                },
                                is_featured=random.choice([True, False]),
                                rating=round(random.uniform(3.0, 5.0), 1)
                            )
                            
                            events_created += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"✅ Created event: {nombre_lugar_text} on {fecha_inicio} - ${precio}")
                            )
                        else:
                            self.stdout.write(
                                self.style.WARNING(f"⚠️ Event not in {city}: {ubicacion}")
                            )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"⚠️ Could not extract location info for: {event_data['slug']}")
                        )

                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️ Error processing {event_data['slug']}: {e}")
                    )
                    continue

                # Esperar entre requests para no sobrecargar el servidor
                time.sleep(2)

            self.stdout.write(f"🎉 Total events created: {events_created}")

        except Exception as e:
            self.stderr.write(f"❌ Error during scraping: {e}")
        finally:
            if driver:
                driver.quit()
                self.stdout.write("🔚 Chrome driver closed")