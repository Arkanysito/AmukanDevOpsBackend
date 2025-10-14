from django.contrib import admin

from .models import (
    CustomUser,
    Interest,
    TravelerType,
    UserFavorite,
    UserInterest,
    UserTravelerTypeHistory,
)


class UserFavoriteInline(admin.TabularInline):
    model = UserFavorite
    extra = 0
    fields = ('content_type', 'object_id')

class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'traveler_type_name')
    inlines = [UserFavoriteInline]

    def traveler_type_name(self, obj):
        return obj.traveler_type_id.name if obj.traveler_type_id else '-'
    traveler_type_name.short_description = 'Traveler Type'

class TravelerTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'recommendation_model_version', 'created_at')

class InterestAdmin(admin.ModelAdmin):
    list_display = ('name',)

class UserInterestAdmin(admin.ModelAdmin):
    list_display = ('user_username', 'interest_name', 'weight')
    
    def user_username(self, obj):
        return obj.user_id.username
    user_username.short_description = 'User'

    def interest_name(self, obj):
        return obj.interest_id.name
    interest_name.short_description = "Interest"

class UserFavoriteAdmin(admin.ModelAdmin):
    list_display = ("user_username", "content_type", "object_id", "user_fav_id")
    list_filter = ("content_type",)
    search_fields = ("user__username", "user__email", "object_id")

    def user_username(self, obj):
        return obj.user.username

    user_username.short_description = "User"

admin.site.register(TravelerType, TravelerTypeAdmin)
admin.site.register(CustomUser, UserAdmin)
admin.site.register(Interest, InterestAdmin)
admin.site.register(UserInterest, UserInterestAdmin)
admin.site.register(UserTravelerTypeHistory)
admin.site.register(UserFavorite, UserFavoriteAdmin)