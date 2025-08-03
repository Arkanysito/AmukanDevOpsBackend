from django.contrib import admin
from .models import TravelerType, User, Interest, UserInterest, UserTravelerTypeHistory

admin.site.register(TravelerType)
admin.site.register(User)
admin.site.register(Interest)
admin.site.register(UserInterest)
admin.site.register(UserTravelerTypeHistory)
