# amukan/urls.py
from django.contrib import admin
from django.urls import path, include
from apps.core.views import ChoicesView
from apps.core.views import get_org_dashboard_embed_url
from apps.recommendation.views import recommend_places_view, recommend_services_view 
from apps.core.views import upload_image
from apps.organizations.views import login_view, get_user_profile

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/destination/', include('apps.destinationSearch.urls')),
    path('api/user/', include('apps.users.urls')),
    path('api/travel/', include('apps.travel.urls')),
    path('api-auth/', include("rest_framework.urls")),
    path("api/metabase/org-dashboard", get_org_dashboard_embed_url),
    path("api/experiences/", include("apps.experiences.urls")),
    
    path("api/recommendations/", recommend_places_view, name="recommend_places"),
    path("api/recommendations/services/", recommend_services_view, name="recommend_services"),

    path("api/uploads/direct", upload_image),
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/user/', get_user_profile, name='user-profile'),
    path('api/choices/', ChoicesView.as_view(), name='choices'),
    path('api/location/', include("apps.location.urls")),
    path('api/', include('apps.booking.urls')),
]