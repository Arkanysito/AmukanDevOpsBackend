from django.urls import path
from .views import create_service 

urlpatterns = [
    path("services/", create_service, name="create-service"),
]
