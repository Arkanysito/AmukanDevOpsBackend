from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from shapely import wkt
import osmnx as ox
import pandas as pd
from apps.location.models import Place, Zone
from apps.organizations.models import Organization
from apps.core.constants import PlaceType, ZoneLevel

class Command(BaseCommand):
    help = "Importa puntos de interés desde OpenStreetMap para la comuna de Viña del Mar"

    def handle(self, *args, **kwargs):
        # Buscar comuna
        comuna = Zone.objects.filter(name__icontains="Viña del Mar", level=ZoneLevel.DISTRICT).first()
        if not comuna:
            self.stdout.write(self.style.ERROR("❌ Comuna Viña del Mar no encontrada"))
            return

        # Convertir geometría GEOS → Shapely
        polygon = wkt.loads(comuna.coordinates.wkt)

        # Tags relevantes en OSM
        tags = {
            "tourism": True,
            "amenity": True, 
            "leisure": True,
            "historic": True,
            "shop": True,
            "public_transport": True,
            "highway": ["bus_stop"],
            "railway": ["station"],
            "natural": ["beach", "spring", "cave_entrance"],
            "aerialway": True,
            "aeroway": True,
            "craft": True,
            "office": True,
            "landuse": True
        }

        # Obtener POIs desde OSM
        gdf = ox.features_from_polygon(polygon, tags=tags)
        gdf = gdf[gdf.geometry.type == "Point"]
        gdf = gdf[gdf["name"].notnull()]

        org = Organization.objects.first()
        created_count = 0
        skipped_count = 0

        # Obtener todos los valores válidos de PlaceType
        valid_place_types = {pt.value for pt in PlaceType}
        
        for _, row in gdf.iterrows():
            name = row["name"]
            lon, lat = row.geometry.x, row.geometry.y
            point = Point(lon, lat)

            # Encontrar el tipo de OSM
            raw_tipo = None
            for tag_category in ['amenity', 'tourism', 'leisure', 'historic', 'shop', 
                               'public_transport', 'highway', 'railway', 'natural']:
                if tag_category in row and not pd.isna(row[tag_category]):
                    raw_tipo = str(row[tag_category])
                    break
            
            # Usar el tipo de OSM directamente si existe en PlaceType, sino usar UNKNOWN
            if raw_tipo and raw_tipo in valid_place_types:
                place_type = raw_tipo
            else:
                place_type = PlaceType.UNKNOWN.value

            # Evitar duplicados
            existing = Place.objects.filter(
                name=name, 
                coordinates__distance_lte=(point, 5)  # 5 metros de tolerancia
            ).first()
            
            if existing:
                skipped_count += 1
                if skipped_count <= 10:  # Mostrar solo los primeros 10 duplicados
                    self.stdout.write(f"ℹ️ POI ya existe: {name}")
                continue

            # Crear el lugar
            Place.objects.create(
                name=name,
                coordinates=point,
                organization_id=org,
                zone_id=comuna,
                type=place_type,
                description=f"POI importado desde OpenStreetMap. Tipo OSM: {raw_tipo or 'desconocido'}",
                rating=0.0
            )
            created_count += 1
            if created_count <= 20:  # Mostrar solo los primeros 20 creados
                self.stdout.write(self.style.SUCCESS(f"✅ POI creado: {name} ({place_type})"))

        self.stdout.write(self.style.SUCCESS(
            f"\n🎉 Importación completada: {created_count} nuevos POIs, {skipped_count} existentes omitidos"
        ))