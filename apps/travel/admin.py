from django.contrib import admin
from .models import Itinerary, ItineraryCollaborator, ItineraryItem

class ItineraryCollaboratorAdmin(admin.ModelAdmin):
    list_display = ('user_username', 'role')

    def user_username(self, obj):
        return obj.user_id.username
    user_username.short_description = 'User'

class ItineraryAdmin(admin.ModelAdmin):
    list_display = ('name',)

class ItineraryItemAdmin(admin.ModelAdmin):
    list_display = ('item_id', 'scheduled_date', 'reservable_name', 'estimated_cost', 'estimated_cost_currency')

    def reservable_name(self, obj):
        return str(obj.reservable) if obj.reservable else '—'
    reservable_name.short_description = 'Reservable'

admin.site.register(Itinerary, ItineraryAdmin)
admin.site.register(ItineraryCollaborator, ItineraryCollaboratorAdmin)
admin.site.register(ItineraryItem, ItineraryItemAdmin)
