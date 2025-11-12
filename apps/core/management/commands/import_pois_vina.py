from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
import requests
import json
import time
import uuid
import mimetypes
import os
import traceback 
from urllib.parse import unquote
import datetime

from django.core.cache import cache
from apps.location.models import Place, Zone
from apps.organizations.models import Organization
from apps.core.constants import PlaceType, ZoneLevel, OrganizationCategory
from apps.core.models import Image

import boto3
from django.core.files.base import ContentFile
from botocore.exceptions import NoCredentialsError


class Command(BaseCommand):
    help = "Importa y enriquece puntos de interés desde OpenStreetMap para Viña del Mar"

    # Variable de sesión de S3
    s3_client = None
    # Variable para el bucket
    TARGET_BUCKET = None

    def get_s3_client(self):
        """
        Inicializa y devuelve el cliente de Boto3 para MinIO,
        leyendo las credenciales desde las variables de entorno.
        """
        if self.s3_client:
            return self.s3_client
            
        try:
            # Leemos directo de las variables de entorno que
            # docker-compose está pasando al contenedor.
            
            access_key = os.environ.get('AWS_ACCESS_KEY_ID')
            secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
            endpoint_url = os.environ.get('S3_ENDPOINT_URL')
            region = os.environ.get('S3_REGION')
            self.TARGET_BUCKET = os.environ.get('S3_BUCKET_NAME')

            if not all([access_key, secret_key, endpoint_url, self.TARGET_BUCKET]):
                self.stdout.write(self.style.ERROR(
                    "❌ Error fatal: Faltan variables de entorno (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_ENDPOINT_URL, S3_BUCKET_NAME)."
                ))
                return None

            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
                endpoint_url=endpoint_url
            )
            return self.s3_client
            
        except NoCredentialsError as e:
            self.stdout.write(self.style.ERROR(f"❌ Error fatal: Credenciales de S3 no encontradas. {e}"))
            return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error fatal al conectar con S3 (MinIO): {e}"))
            return None

    def get_osm_data(self, polygon_wkt):
        """Obtiene datos de OSM usando Overpass API"""
        from shapely import wkt
        geometry = wkt.loads(polygon_wkt)
        
        if geometry.geom_type == 'MultiPolygon':
            poly = list(geometry.geoms)[0]
        else:
            poly = geometry
        
        coords = list(poly.exterior.coords)
        polygon_str = " ".join([f"{lat} {lon}" for lon, lat in coords])
        
        overpass_query = f"""
        [out:json][timeout:90];
        (
          node["tourism"](poly:"{polygon_str}");
          node["amenity"](poly:"{polygon_str}");
          node["leisure"](poly:"{polygon_str}");
          node["historic"](poly:"{polygon_str}");
          node["shop"](poly:"{polygon_str}");
          node["public_transport"](poly:"{polygon_str}");
          node["highway"="bus_stop"](poly:"{polygon_str}");
          node["railway"="station"](poly:"{polygon_str}");
          node["natural"](poly:"{polygon_str}");
          node["aerialway"](poly:"{polygon_str}");
          node["aeroway"](poly:"{polygon_str}");
          node["craft"](poly:"{polygon_str}");
          node["office"](poly:"{polygon_str}");
          node["landuse"](poly:"{polygon_str}");
        );
        out body;
        >;
        out skel qt;
        """
        
        try:
            self.stdout.write(f"🔍 Consultando Overpass API...")
            response = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={'data': overpass_query},
                timeout=120
            )
            response.raise_for_status()
            self.stdout.write(self.style.SUCCESS("✅ Datos obtenidos de Overpass API"))
            return response.json()
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"❌ Error al consultar Overpass API: {e}"))
            return None

    def get_bounding_box(self, polygon_wkt):
        """Obtiene bounding box como alternativa si el polígono es muy complejo"""
        from shapely import wkt
        geometry = wkt.loads(polygon_wkt)
        bounds = geometry.bounds
        return f"{bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]}"

    def get_osm_data_bbox(self, polygon_wkt):
        """Versión alternativa usando bounding box"""
        bbox = self.get_bounding_box(polygon_wkt)
        
        overpass_query = f"""
        [out:json][timeout:90];
        (
          node["tourism"]({bbox});
          node["amenity"]({bbox});
          node["leisure"]({bbox});
          node["historic"]({bbox});
          node["shop"]({bbox});
          node["public_transport"]({bbox});
          node["highway"="bus_stop"]({bbox});
          node["railway"="station"]({bbox});
          node["natural"]({bbox});
          node["aerialway"]({bbox});
          node["aeroway"]({bbox});
          node["craft"]({bbox});
          node["office"]({bbox});
          node["landuse"]({bbox});
        );
        out body;
        >;
        out skel qt;
        """
        
        try:
            self.stdout.write(f"🔍 Consultando Overpass API con bounding box...")
            response = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={'data': overpass_query},
                timeout=120
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"❌ Error al consultar Overpass API: {e}"))
            return None

    def enrich_with_nominatim(self, name, lat, lon):
        """
        Enriquece datos usando Nominatim API (gratuita)
        """
        cache_key = f"nominatim_{name}_{lat}_{lon}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                'format': 'json',
                'lat': lat,
                'lon': lon,
                'zoom': 18,
                'addressdetails': 1
            }
            
            headers = {
                'User-Agent': 'TravelPlannerApp/1.0'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                enriched_data = {
                    'display_name': data.get('display_name', ''),
                    'address': data.get('address', {}),
                    'type': data.get('type', ''),
                    'category': data.get('category', ''),
                }
                
                cache.set(cache_key, enriched_data, 60*60*24*30)
                return enriched_data
                
        except Exception as e:
            self.stdout.write(f"⚠️ Error Nominatim para {name}: {e}")
        
        return None

    def extract_accessibility_features(self, tags):
        """Extrae características de accesibilidad de los tags OSM"""
        accessibility_features = {}
        
        # Mapeo de tags OSM a características de accesibilidad
        accessibility_mapping = {
            'wheelchair': {
                'yes': ['wheelchair_accessible'],
                'limited': ['wheelchair_accessible'],
                'no': []
            },
            'internet_access': {
                'yes': ['wifi'],
                'wifi': ['wifi'],
                'no': []
            },
            'toilets:wheelchair': {
                'yes': ['accessible_restrooms']
            },
            'parking:wheelchair': {
                'yes': ['accessible_parking']
            }
        }
        
        features = []
        for tag, values in accessibility_mapping.items():
            if tag in tags:
                tag_value = tags[tag]
                if tag_value in values:
                    features.extend(values[tag_value])
        
        return list(set(features))  # Remover duplicados

    def extract_schedule(self, tags):
        """Extrae horarios de los tags OSM"""
        schedule = {}
        
        if 'opening_hours' in tags:
            schedule['opening_hours'] = tags['opening_hours']
        
        # Puedes expandir esto para otros formatos de horario
        if 'opening_hours:covid19' in tags:
            schedule['special_hours'] = tags['opening_hours:covid19']
            
        return schedule if schedule else None

    def estimate_quality_from_tags(self, tags):
        """
        Estima calidad basada en tags reales de OSM
        Sin inventar ratings, usando características objetivas
        """
        base_score = 3.0
        
        # Factores positivos basados en amenities reales
        positive_factors = {
            'internet_access': {'wifi': 0.4, 'yes': 0.3},
            'air_conditioning': {'yes': 0.3},
            'outdoor_seating': {'yes': 0.2},
            'wheelchair': {'yes': 0.2},
            'takeaway': {'yes': 0.1},
            'delivery': {'yes': 0.1},
            'brewery': {'yes': 0.3},
            'microbrewery': {'yes': 0.4},
        }
        
        # Ajustar score basado en factores reales
        for factor, values in positive_factors.items():
            if factor in tags:
                tag_value = tags[factor]
                if tag_value in values:
                    base_score += values[tag_value]
        
        # Limitar entre 2.5 y 4.5 (no perfecto, pero tampoco malo)
        return max(2.5, min(4.5, round(base_score, 1)))

    def get_realistic_price_estimate(self, place_type, tags):
        """
        Precios realistas basados en datos de Chile
        Usando rangos conservadores
        """
        # Precios base en CLP para Chile
        price_ranges = {
            # Alojamientos (por noche)
            PlaceType.HOTEL.value: (25000, 80000),
            PlaceType.HOSTEL.value: (8000, 20000),
            PlaceType.GUEST_HOUSE.value: (15000, 35000),
            PlaceType.APARTMENT.value: (20000, 50000),
            PlaceType.RESORT.value: (50000, 120000),
            PlaceType.BED_BREAKFAST.value: (12000, 25000),
            PlaceType.MOTEL.value: (10000, 25000),
            PlaceType.CAMPSITE.value: (5000, 15000),
            
            # Comida (por persona)
            PlaceType.RESTAURANT.value: (8000, 20000),
            PlaceType.CAFE.value: (3000, 8000),
            PlaceType.BAR.value: (5000, 12000),
            PlaceType.PUB.value: (4000, 10000),
            PlaceType.FAST_FOOD.value: (2000, 6000),
            
            # Actividades (entrada)
            PlaceType.MUSEUM.value: (0, 8000),
            PlaceType.GALLERY.value: (0, 5000),
            PlaceType.CINEMA.value: (4000, 7000),
            PlaceType.THEATRE.value: (5000, 15000),
            PlaceType.ZOO.value: (6000, 12000),
            PlaceType.AQUARIUM.value: (5000, 10000),
            
            # Gratis
            PlaceType.PARK.value: (0, 0),
            PlaceType.BEACH.value: (0, 0),
            PlaceType.VIEWPOINT.value: (0, 0),
            PlaceType.LIBRARY.value: (0, 0),
        }
        
        min_price, max_price = price_ranges.get(place_type, (3000, 8000))
        
        # Ajustar basado en características específicas
        if 'internet_access' in tags and tags['internet_access'] == 'wifi':
            min_price = int(min_price * 1.1)
            max_price = int(max_price * 1.1)
            
        if 'air_conditioning' in tags and tags['air_conditioning'] == 'yes':
            min_price = int(min_price * 1.15)
            max_price = int(max_price * 1.15)
        
        # Usar precio promedio del rango
        average_price = (min_price + max_price) // 2
        
        # Redondear a múltiplo de 500
        return round(average_price / 500) * 500

    def create_enhanced_description(self, tags, nominatim_data):
        """Crea descripción enriquecida con información real"""
        description_parts = []
        
        # Información básica del tipo
        for category in ['tourism', 'amenity', 'leisure', 'shop']:
            if category in tags:
                description_parts.append(f"Tipo: {tags[category]}")
                break
        
        # Características específicas
        features = []
        if tags.get('internet_access') == 'wifi':
            features.append("Wi-Fi disponible")
        if tags.get('outdoor_seating') == 'yes':
            features.append("Terraza exterior")
        if tags.get('wheelchair') == 'yes':
            features.append("Accesible para sillas de ruedas")
        if tags.get('air_conditioning') == 'yes':
            features.append("Aire acondicionado")
        if tags.get('takeaway') == 'yes':
            features.append("Comida para llevar")
        if tags.get('delivery') == 'yes':
            features.append("Delivery disponible")
            
        if features:
            description_parts.append("Servicios: " + ", ".join(features))
        
        # Información de contacto si está disponible
        if 'phone' in tags:
            description_parts.append(f"Contacto: {tags['phone']}")
        
        return ". ".join(description_parts)

    def map_osm_type_to_placetype(self, osm_tags):
        """Mapea tipos de OSM a PlaceType"""
        type_mapping = {
            # Tourism
            'hotel': PlaceType.HOTEL.value,
            'hostel': PlaceType.HOSTEL.value,
            'guest_house': PlaceType.GUEST_HOUSE.value,
            'resort': PlaceType.RESORT.value,
            'bed_and_breakfast': PlaceType.BED_BREAKFAST.value,
            'motel': PlaceType.MOTEL.value,
            'camp_site': PlaceType.CAMPSITE.value,
            'attraction': PlaceType.ATTRACTION.value,
            'museum': PlaceType.MUSEUM.value,
            'gallery': PlaceType.GALLERY.value,
            'art_gallery': PlaceType.ART_GALLERY.value,
            'viewpoint': PlaceType.VIEWPOINT.value,
            'zoo': PlaceType.ZOO.value,
            'aquarium': PlaceType.AQUARIUM.value,
            'theme_park': PlaceType.ADVENTURE_PARK.value,
            
            # Amenity
            'restaurant': PlaceType.RESTAURANT.value,
            'cafe': PlaceType.CAFE.value,
            'bar': PlaceType.BAR.value,
            'pub': PlaceType.PUB.value,
            'fast_food': PlaceType.FAST_FOOD.value,
            'library': PlaceType.LIBRARY.value,
            'cinema': PlaceType.CINEMA.value,
            'theatre': PlaceType.THEATRE.value,
            'nightclub': PlaceType.NIGHTCLUB.value,
            'bank': PlaceType.BANK.value,
            'pharmacy': PlaceType.PHARMACY.value,
            'hospital': PlaceType.HOSPITAL.value,
            'clinic': PlaceType.CLINIC.value,
            'police': PlaceType.POLICE.value,
            'fire_station': PlaceType.FIRE_STATION.value,
            'post_office': PlaceType.POST_OFFICE.value,
            'university': PlaceType.UNIVERSITY.value,
            'college': PlaceType.COLLEGE.value,
            'school': PlaceType.SCHOOL.value,
            'parking': PlaceType.PARKING.value,
            'bus_station': PlaceType.BUS_STATION.value,
            'taxi': PlaceType.TAXI_STAND.value,
            'car_rental': PlaceType.CAR_RENTAL.value,
            'marketplace': PlaceType.MARKET.value,
            
            # Leisure
            'park': PlaceType.PARK.value,
            'garden': PlaceType.BOTANICAL_GARDEN.value,
            'golf_course': PlaceType.GOLF_COURSE.value,
            'stadium': PlaceType.STADIUM.value,
            'sports_centre': PlaceType.SPORTS_CENTRE.value,
            'swimming_pool': PlaceType.SWIMMING_POOL.value,
            'fitness_centre': PlaceType.FITNESS_CENTRE.value,
            
            # Shop
            'supermarket': PlaceType.SUPERMARKET.value,
            'mall': PlaceType.SHOPPING_MALL.value,
            'department_store': PlaceType.DEPARTMENT_STORE.value,
            'convenience': PlaceType.CONVENIENCE_STORE.value,
            'clothes': PlaceType.CLOTHING_STORE.value,
            'bakery': PlaceType.BAKERY.value,
            'books': PlaceType.BOOKS.value,
            
            # Natural
            'beach': PlaceType.BEACH.value,
            'spring': PlaceType.HOT_SPRING.value,
            
            # Railway
            'station': PlaceType.TRAIN_STATION.value,
            
            # Highway
            'bus_stop': PlaceType.BUS_STOP.value,
        }
        
        for category in ['tourism', 'amenity', 'leisure', 'shop', 'natural', 'railway', 'highway']:
            if category in osm_tags:
                osm_type = osm_tags[category]
                if osm_type in type_mapping:
                    return type_mapping[osm_type]
        
        return PlaceType.UNKNOWN.value

    # --- Función de API de Wikimedia ---
    def get_wikimedia_image_url(self, file_title):
        """
        Obtiene la URL de una imagen desde la API de Wikimedia Commons.
        Espera un título como 'File:Some_Image.jpg'.
        """
        # Asegurarse de que el título tenga el prefijo 'File:'
        if not file_title.startswith('File:'):
            file_title = f"File:{file_title}"
            
        WIKI_API_URL = "https://commons.wikimedia.org/w/api.php"
        
        params = {
            "action": "query",
            "format": "json",
            "titles": file_title,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 800  # Pedimos un thumbnail de 800px de ancho
        }
        
        headers = {
            'User-Agent': 'TravelPlannerApp/1.0 (python-requests)'
        }
        
        try:
            # Hacemos la petición a la API de Wikimedia
            response = requests.get(WIKI_API_URL, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # La estructura de la API de MediaWiki es anidada
            pages = data.get('query', {}).get('pages', {})
            if not pages:
                self.stdout.write(self.style.WARNING(f"  -> API Wiki: No se encontraron 'pages' para {file_title}"))
                return None

            # Iteramos sobre las páginas (normalmente solo una, con ID -1 si falta)
            for page_id, page_data in pages.items():
                if page_id == "-1":
                    self.stdout.write(self.style.WARNING(f"  -> API Wiki: El archivo {file_title} no existe en Commons."))
                    return None
                    
                if 'imageinfo' in page_data:
                    image_info = page_data['imageinfo'][0]
                    
                    # 'thumburl' es la URL del thumbnail que pedimos (800px)
                    if 'thumburl' in image_info:
                        return image_info['thumburl']
                        
                    # Fallback a la URL original si no hay thumbnail (menos ideal)
                    if 'url' in image_info:
                        return image_info['url']
                        
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"  -> Error API Wikimedia: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> Error procesando API Wikimedia: {e}"))
            
        return None
    
    def get_wikidata_image_info(self, wikidata_id):
        """
        Obtiene el nombre de archivo de la imagen (Propiedad P18) 
        desde la API de Wikidata usando el Q-ID.
        """
        WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
        
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": wikidata_id,
            "props": "claims"
        }
        
        headers = {
            'User-Agent': 'TravelPlannerApp/1.0 (python-requests)'
        }

        try:
            response = requests.get(WIKIDATA_API_URL, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Navegar la estructura de Wikidata
            entities = data.get('entities', {})
            if wikidata_id not in entities:
                return None
            
            claims = entities[wikidata_id].get('claims', {})
            
            # P18 es la propiedad "image" en Wikidata
            if 'P18' in claims:
                # Tomamos la primera imagen
                first_image_claim = claims['P18'][0]
                image_filename = first_image_claim.get('mainsnak', {}).get('datavalue', {}).get('value')
                
                # Esto nos da el nombre del archivo, ej: "El Salto, Viña del Mar.jpg"
                return image_filename
                
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"  -> Error API Wikidata: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> Error procesando API Wikidata: {e}"))
            
        return None


    def handle(self, *args, **kwargs):
        
        s3 = self.get_s3_client()
        if not s3:
            return # La función get_s3_client ya imprimió el error
        
        self.stdout.write(f"Conectado a S3 (MinIO). Usando bucket: {self.TARGET_BUCKET}")
        self.stdout.write("🔧 Obteniendo/creando organización por defecto 'Amukan'...")
        
        try:
            # Asegúrate que 'OrganizationCategory.OTHER' exista en tus constantes
            default_category = OrganizationCategory.OTHER 
            
        except AttributeError:
            self.stdout.write(self.style.ERROR("❌ Error: 'OrganizationCategory.OTHER' no existe en 'apps.core.constants'."))
            self.stdout.write(self.style.ERROR("   Por favor, edita 'import_pois_vina.py' y elige una categoría válida para 'default_category'."))
            return # Detener el script

        try:
            amukan_org, created = Organization.objects.get_or_create(
                name="Amukan",
                defaults={
                    'category': default_category,
                    'email': 'amukanchile.oficial@amukan.cl'
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS("✅ Organización 'Amukan' creada por defecto."))
            else:
                self.stdout.write(self.style.SUCCESS("✅ Organización 'Amukan' encontrada."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error fatal al crear/obtener 'Amukan': {e}"))
            return # Detener el script si no se puede crear la org
        
        
        # Buscar comuna
        comuna = Zone.objects.filter(name__icontains="Viña del Mar", level=ZoneLevel.DISTRICT).first()
        if not comuna:
            self.stdout.write(self.style.ERROR("❌ Comuna Viña del Mar no encontrada"))
            return

        self.stdout.write(f"📍 Importando y enriqueciendo POIs para: {comuna.name}")

        # Obtener datos de OSM
        osm_data = self.get_osm_data(comuna.coordinates.wkt)
        
        if not osm_data:
            self.stdout.write("🔄 Intentando con bounding box...")
            osm_data = self.get_osm_data_bbox(comuna.coordinates.wkt)
            
        if not osm_data:
            self.stdout.write(self.style.ERROR("❌ No se pudieron obtener datos de OSM"))
            return

        # Asignamos None por defecto a organización (Por lógica interna si una mepresaa es dueña nos lo debe comunicar)
        created_count = 0
        skipped_count = 0
        no_name_count = 0

        # Procesar elementos
        for i, element in enumerate(osm_data.get('elements', [])):
            if element['type'] != 'node':
                continue

            # Verificar que tenga nombre
            tags = element.get('tags', {})
            name = tags.get('name', '').strip()
            if not name:
                no_name_count += 1
                continue

            # Crear punto
            point = Point(element['lon'], element['lat'])

            # Mapear tipo
            place_type = self.map_osm_type_to_placetype(tags)

            # Evitar duplicados
            existing = Place.objects.filter(
                name=name, 
                coordinates__distance_lte=(point, 10)
            ).first()
            
            if existing:
                skipped_count += 1
                continue

            # ENRIQUECIMIENTO DE DATOS
            self.stdout.write(f"🔍 Procesando: {name}")
            
            nominatim_data = self.enrich_with_nominatim(name, element['lat'], element['lon'])
            estimated_rating = self.estimate_quality_from_tags(tags)
            estimated_price = self.get_realistic_price_estimate(place_type, tags)
            accessibility_features = self.extract_accessibility_features(tags)
            schedule = self.extract_schedule(tags)
            description = self.create_enhanced_description(tags, nominatim_data)
            address = self.build_address(tags, nominatim_data)
            
            # Pequeña pausa para no saturar Nominatim
            if i % 5 == 0:
                time.sleep(0.5)

            # --- LÓGICA DE IMAGEN ---
            cover_image_obj = None
            image_url = tags.get('image') # 1. Prioridad: tag 'image' (link directo)
            image_filename = None

            # 2. Fallback a wikimedia_commons
            if not image_url:
                image_filename = tags.get('wikimedia_commons')
                if image_filename:
                    self.stdout.write(self.style.HTTP_INFO(f"  -> Encontrado 'wikimedia_commons': {image_filename}"))

            # 3. Fallback a wikidata
            if not image_url and not image_filename:
                wikidata_id = tags.get('wikidata')
                if wikidata_id:
                    self.stdout.write(self.style.HTTP_INFO(f"  -> Buscando en Wikidata con ID: {wikidata_id}"))
                    image_filename = self.get_wikidata_image_info(wikidata_id)
                    if image_filename:
                        self.stdout.write(self.style.HTTP_INFO(f"  -> Archivo encontrado en Wikidata: {image_filename}"))
            
            # Si tenemos un nombre de archivo (de wikidata o wikimedia_commons)
            if image_filename and not image_url:
                image_url = self.get_wikimedia_image_url(image_filename)
                if image_url:
                     self.stdout.write(f"  -> URL de Wikimedia obtenida: {image_url[:50]}...")
                else:
                     self.stdout.write(self.style.WARNING(f"  -> No se pudo obtener URL para {image_filename}"))

            # Si al final de todo tenemos una URL, la descargamos y subimos a S3
            if image_url:
                try:
                    # 1. Descargar la imagen en memoria
                    img_response = requests.get(image_url, timeout=15, headers={'User-Agent': 'TravelPlannerApp/1.0'})
                    img_response.raise_for_status()
                    
                    img_content_bytes = img_response.content
                    img_content_size = len(img_content_bytes)
                    
                    # 2. Definir S3 object_key y metadata
                    parsed_path = requests.utils.urlparse(image_url).path
                    url_encoded_filename = os.path.basename(parsed_path)
                    # Decodificamos el nombre para quitar %2C, %C3%B1, etc.
                    base_filename = unquote(url_encoded_filename)

                    if not base_filename or len(base_filename) > 200: 
                        base_filename = f"{name.replace(' ', '_')}_{element['id']}.jpg"
                    
                    # Replicamos la ruta pública que SÍ funciona
                    now = datetime.datetime.now()
                    s3_object_key = f"images/public/{now.year}/{now.month:02d}/{uuid.uuid4()}/{base_filename}"
                    
                    content_type, _ = mimetypes.guess_type(base_filename)
                    if not content_type:
                        content_type = img_response.headers.get('Content-Type', 'application/octet-stream')

                    # 3. Subir a S3 usando Boto3
                    self.stdout.write(f"  -> Subiendo {s3_object_key} a S3 bucket {self.TARGET_BUCKET}...")
                    s3.put_object(
                        Bucket=self.TARGET_BUCKET, 
                        Key=s3_object_key,
                        Body=img_content_bytes,
                        ContentType=content_type,
                        ACL='public-read'
                    )
                    
                    # 4. Crear el registro en la BD Image con los metadatos correctos
                    cover_image_obj = Image.objects.create(
                        organization_id=amukan_org,
                        object_key=s3_object_key,
                        bucket=self.TARGET_BUCKET, 
                        storage="s3", # Como en tu modelo
                        status=Image.Status.STORED, # ¡La marcamos como guardada!
                        size_bytes=img_content_size,
                        content_type=content_type,
                        filename=base_filename # Guardamos el nombre DECODIFICADO
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f"    🖼️  Foto subida y guardada: {s3_object_key}"))

                except requests.exceptions.RequestException as e:
                    self.stdout.write(self.style.ERROR(f"    ❌ Error descargando imagen {image_url}: {e}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    ❌ Error procesando/subiendo imagen: {e}"))
                    traceback.print_exc() # Imprime el error detallado
            


            # Crear el lugar con todos los datos enriquecidos
            try:
                place_data = {
                    'name': name,
                    'coordinates': point,
                    'organization_id': amukan_org,
                    'zone_id': comuna,
                    'type': place_type,
                    'description': description,
                    'address': address,
                    'rating': estimated_rating,
                    'average_price': estimated_price,
                }
                
                # Agregar campos opcionales solo si tienen datos
                if accessibility_features:
                    place_data['accessibility_features'] = accessibility_features
                if schedule:
                    place_data['schedule'] = schedule
                
                # Asignar la imagen
                if cover_image_obj:
                    place_data['cover_image'] = cover_image_obj
                
                Place.objects.create(**place_data)
                
                created_count += 1
                
                if created_count <= 15:
                    price_info = f" - 💰 ${estimated_price}" if estimated_price > 0 else " - 🆓 Gratis"
                    self.stdout.write(self.style.SUCCESS(
                        f"✅ {name} ({place_type}) - ⭐ {estimated_rating}{price_info}"
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error creando {name}: {e}"))
                traceback.print_exc()

        self.stdout.write(self.style.SUCCESS(
            f"\n🎉 Importación completada:\n"
            f"   • {created_count} nuevos POIs creados\n"
            f"   • {skipped_count} existentes omitidos\n"
            f"   • {no_name_count} sin nombre"
        ))

    def build_address(self, tags, nominatim_data):
        """Construye dirección usando datos de OSM y Nominatim"""
        # Primero intentar con OSM
        if 'addr:street' in tags and 'addr:housenumber' in tags:
            return f"{tags['addr:street']} {tags['addr:housenumber']}"
        elif 'addr:street' in tags:
            return tags['addr:street']
        
        # Fallback a Nominatim
        if nominatim_data and 'address' in nominatim_data:
            address = nominatim_data['address']
            if 'road' in address and 'house_number' in address:
                return f"{address['road']} {address['house_number']}"
            elif 'road' in address:
                return address['road']
            elif 'display_name' in nominatim_data:
                # Usar solo la primera parte del display_name
                return nominatim_data['display_name'].split(',')[0]
        
        return "Dirección no especificada"