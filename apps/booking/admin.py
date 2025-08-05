from django.contrib import admin
from .models import Reservation

class ReservationAdmin(admin.ModelAdmin):
    list_display = ('user_username', 'object_content_type')

    def user_username(self, obj):
        return obj.user_id.username
    user_username.short_description = 'User'

    def object_content_type(self, obj):
        return obj.content_type.model
    object_content_type.short_description = "Object Type"

admin.site.register(Reservation, ReservationAdmin)