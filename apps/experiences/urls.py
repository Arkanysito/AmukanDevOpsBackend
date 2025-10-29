from django.urls import path
from .views import get_user_services, create_service, get_service_detail, update_service, delete_service, list_events, create_event, get_event_detail, update_event, delete_event

urlpatterns = [
    path('services/', get_user_services, name='get-user-services'),
    path('services/create/', create_service, name='create-service'),
    path('services/<str:service_type>/<uuid:service_id>/', get_service_detail, name='get-service-detail'),
    path('services/<str:service_type>/<uuid:service_id>/update/', update_service, name='update-service'),
    path('services/<str:service_type>/<uuid:service_id>/delete/', delete_service, name='delete-service'),
    path('events/', list_events, name='list-events'),
    path('events/create/', create_event, name='create-event'),
    path('events/<uuid:event_id>/', get_event_detail, name='get-event-detail'),
    path('events/<uuid:event_id>/update/', update_event, name='update-event'),
    path('events/<uuid:event_id>/delete/', delete_event, name='delete-event'),
]
