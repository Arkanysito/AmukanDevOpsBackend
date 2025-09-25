from django.urls import path
from .views import get_user_services, create_service, get_service_detail, update_service, delete_service

urlpatterns = [
    path('services/', get_user_services, name='get-user-services'),
    path('services/create/', create_service, name='create-service'),
    path('services/<str:service_type>/<uuid:service_id>/', get_service_detail, name='get-service-detail'),
    path('services/<str:service_type>/<uuid:service_id>/update/', update_service, name='update-service'),
    path('services/<str:service_type>/<uuid:service_id>/delete/', delete_service, name='delete-service'),
]
