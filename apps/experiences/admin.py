from django.contrib import admin
from .models import Service, ServiceType, Event

admin.site.register(ServiceType)
admin.site.register(Service)
admin.site.register(Event)