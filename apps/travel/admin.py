from django.contrib import admin
from .models import Itinerary, ItineraryCollaborator, ItineraryItem

admin.site.register(Itinerary)
admin.site.register(ItineraryCollaborator)
admin.site.register(ItineraryItem)
