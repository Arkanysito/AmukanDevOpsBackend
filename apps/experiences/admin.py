from django.contrib import admin
from .models import AccommodationService, ActivityService, Event

class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name','price', 'service_id')

class EventAdmin(admin.ModelAdmin):
    list_display = ('name','price', 'event_id')

admin.site.register(AccommodationService, ServiceAdmin)
admin.site.register(ActivityService, ServiceAdmin)
admin.site.register(Event, EventAdmin)