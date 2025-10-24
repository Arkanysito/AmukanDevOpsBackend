"""
URL configuration for amukan project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from apps.core.views import ChoicesView
from apps.core.views import get_org_dashboard_embed_url
from apps.recommendation.views import recommend_places_view
from apps.core.views import upload_image

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/destination/', include('apps.destinationSearch.urls')),
    path('api/user/', include('apps.users.urls')),
    path('api/travel/', include('apps.travel.urls')),
    path('api-auth/', include("rest_framework.urls")),
    path("api/metabase/org-dashboard", get_org_dashboard_embed_url),
    path("api/experiences/", include("apps.experiences.urls")),
    path("api/recommendations/", recommend_places_view, name="recommend_places"),
    path("api/uploads/direct", upload_image),
    path('api/choices/', ChoicesView.as_view(), name='choices'),
]
