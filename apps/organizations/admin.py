from django.contrib import admin
from .models import Organization, OrganizationUser

class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'subscription_plan')

class OrganizationUserAdmin(admin.ModelAdmin):
    list_display = ('user_username', 'role')

    def user_username(self, obj):
        return obj.user_id.username
    user_username.short_description = 'User'

admin.site.register(OrganizationUser, OrganizationUserAdmin)
admin.site.register(Organization, OrganizationAdmin)