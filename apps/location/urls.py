# apps/location/urls.py
from django.urls import path
from .views import (
    create_place, 
    list_places,
    get_place_detail, 
    update_place, 
    delete_place,
    list_zones,
    get_info_from_coords
)

urlpatterns = [
    path('create/', create_place, name='create-place'),
    path('list/', list_places, name='list-places'),
    path('zones/', list_zones, name='list-zones'),
    path('get-info-from-coords/', get_info_from_coords, name='get-info-from-coords'),
    
    path('<str:place_id>/', get_place_detail, name='get-place-detail'),
    path('<str:place_id>/update/', update_place, name='update-place'),
    path('<str:place_id>/delete/', delete_place, name='delete-place'),
]