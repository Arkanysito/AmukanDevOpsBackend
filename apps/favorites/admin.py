from django.contrib import admin
from .models import UserFavorite

@admin.register(UserFavorite)
class UserFavoriteAdmin(admin.ModelAdmin):
    list_display = ("user_fav_id", "user", "content_type", "object_id")
    list_filter = ("content_type",)
    search_fields = ("user__username", "object_id")