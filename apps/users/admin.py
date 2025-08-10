from django.contrib import admin
from .models import TravelerType, CustomUser, Interest, UserInterest, UserTravelerTypeHistory

class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'traveler_type_name')

    def traveler_type_name(self, obj):
        return obj.traveler_type_id.name if obj.traveler_type_id else '-'
    traveler_type_name.short_description = 'Traveler Type'

class TravelerTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'recommendation_model_version', 'created_at')

class InterestAdmin(admin.ModelAdmin):
    list_display = ('name',)

class UserInterestAdmin(admin.ModelAdmin):
    list_display = ('user_username', 'intereset_name', 'weight')
    
    def user_username(self, obj):
        return obj.user_id.username
    user_username.short_description = 'User'

    def intereset_name(self, obj):
        return obj.content_type.model
    intereset_name.short_description = "Interest"


admin.site.register(TravelerType, TravelerTypeAdmin)
admin.site.register(CustomUser, UserAdmin)
admin.site.register(Interest, InterestAdmin)
admin.site.register(UserInterest, UserInterestAdmin)
admin.site.register(UserTravelerTypeHistory)
