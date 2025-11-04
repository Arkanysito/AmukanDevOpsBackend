from django.contrib import admin
from .models import Interaction

class InteractionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'action', 'interaction_date')

admin.site.register(Interaction, InteractionAdmin)
