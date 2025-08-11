from django.contrib import admin
from .models import Interaction, InteractionStats


class InteractionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'action', 'interaction_date')

admin.site.register(Interaction, InteractionAdmin)
admin.site.register( InteractionStats)
