from django.core.management.base import BaseCommand
from django.contrib.gis.geos import GEOSGeometry
import requests
from apps.location.models import Zone
from apps.core.constants import ZoneLevel
from django.contrib.gis.geos import MultiPolygon


class Command(BaseCommand):
    help = "Importa comunas de Chile desde ArcGIS"

    def handle(self, *args, **kwargs):
        url = "https://services.arcgis.com/82C0E4OYu0hT3hkh/arcgis/rest/services/Chile_Comunas_ComunaNames/FeatureServer/0/query"
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "returnGeometry": "true"
        }

        response = requests.get(url, params=params)
        data = response.json()

        for feature in data["features"]:
            props = feature["properties"]
            nombre = props.get("NOM_COM", "").title()
            geometry = feature["geometry"]

            try:
                geom = GEOSGeometry(str(geometry))
                if geom.geom_type == "Polygon":
                    geom = MultiPolygon(geom)

                existing = Zone.objects.filter(name=nombre, level=ZoneLevel.DISTRICT).first()
                if existing:
                    print(f"ℹ️ Comuna ya existe: {nombre}")
                else:
                    Zone.objects.get_or_create(
                        name=nombre,
                        level=ZoneLevel.DISTRICT,
                        defaults={"coordinates": geom}
                    )
                    self.stdout.write(self.style.SUCCESS(f"✅ Comuna creada: {nombre}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Error con {nombre}: {e}"))