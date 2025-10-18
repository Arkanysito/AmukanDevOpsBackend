from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
import requests
import json
import time
from django.core.cache import cache
from apps.location.models import Place, Zone
from apps.organizations.models import Organization
from apps.core.constants import PlaceType, ZoneLevel

class Command(BaseCommand):
    help = "Importa y enriquece puntos de interés desde OpenStreetMap para Viña del Mar"

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

    def handle(self, *args, **kwargs):
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

        org = Organization.objects.first()
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
            
            # 1. Obtener datos de Nominatim para dirección mejorada
            nominatim_data = self.enrich_with_nominatim(name, element['lat'], element['lon'])
            
            # 2. Estimar calidad basada en tags reales
            estimated_rating = self.estimate_quality_from_tags(tags)
            
            # 3. Obtener precio realista
            estimated_price = self.get_realistic_price_estimate(place_type, tags)
            
            # 4. Extraer características de accesibilidad
            accessibility_features = self.extract_accessibility_features(tags)
            
            # 5. Extraer horarios
            schedule = self.extract_schedule(tags)
            
            # 6. Crear descripción enriquecida
            description = self.create_enhanced_description(tags, nominatim_data)
            
            # 7. Construir dirección
            address = self.build_address(tags, nominatim_data)
            
            # Pequeña pausa para no saturar Nominatim
            if i % 5 == 0:
                time.sleep(0.5)

            # Crear el lugar con todos los datos enriquecidos
            try:
                place_data = {
                    'name': name,
                    'coordinates': point,
                    'organization_id': org,
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
                
                Place.objects.create(**place_data)
                
                created_count += 1
                
                if created_count <= 15:
                    price_info = f" - 💰 ${estimated_price}" if estimated_price > 0 else " - 🆓 Gratis"
                    self.stdout.write(self.style.SUCCESS(
                        f"✅ {name} ({place_type}) - ⭐ {estimated_rating}{price_info}"
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error creando {name}: {e}"))

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