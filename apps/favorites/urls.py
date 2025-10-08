from django.urls import path
from . import views

urlpatterns = [
    path("", views.list_user_favorites, name="favorites-list"),
    path("add/", views.add_user_favorite, name="favorites-add"),
    path("remove/", views.remove_user_favorite, name="favorites-remove"),
    path("toggle/", views.toggle_user_favorite, name="favorites-toggle"),
]