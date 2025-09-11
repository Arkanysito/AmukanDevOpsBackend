from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from shapely import wkt
import osmnx as ox
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
            "historic": True
        }

        # Obtener POIs desde OSM
        gdf = ox.features_from_polygon(polygon, tags=tags)
        gdf = gdf[gdf.geometry.type == "Point"]
        gdf = gdf[gdf["name"].notnull()]

        org = Organization.objects.first()

        for _, row in gdf.iterrows():
            name = row["name"]
            lon, lat = row.geometry.x, row.geometry.y
            point = Point(lon, lat)

            raw_tipo = row.get("amenity") or row.get("tourism") or row.get("leisure") or row.get("historic") or "other"
            tipo = str(raw_tipo).split(";")[0].strip()[:20]

            # Evitar duplicados
            existing = Place.objects.filter(name=name, coordinates=point).first()
            if existing:
                self.stdout.write(f"ℹ️ POI ya existe: {name}")
                continue

            Place.objects.create(
                name=name,
                coordinates=point,
                organization_id=org,
                zone_id=comuna,
                type=tipo[:20],
                description=f"POI importado desde OpenStreetMap ({tipo})",
                rating=0.0
            )
            self.stdout.write(self.style.SUCCESS(f"✅ POI creado: {name} ({tipo})"))