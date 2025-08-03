from django.contrib import admin
from .models import Organization, OrganizationUser

admin.site.register(OrganizationUser)
admin.site.register(Organization)