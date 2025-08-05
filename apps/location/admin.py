from django.contrib.gis.admin import GISModelAdmin
from django.contrib import admin
from django.contrib.gis.forms.widgets import OSMWidget
from .models import Zone, Place

class CustomGeoAdmin(GISModelAdmin):
    list_display = ('name',)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if hasattr(field.widget, 'map_srid'):
            field.widget = OSMWidget(attrs={
                'default_lon': -71.5523,
                'default_lat': -33.0245,
                'default_zoom': 12,
            })
        return field

@admin.register(Zone)
class ZoneAdmin(CustomGeoAdmin):
    pass

@admin.register(Place)
class PlaceAdmin(CustomGeoAdmin):
    pass
