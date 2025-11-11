# apps/booking/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookingViewSet

router = DefaultRouter()

# 2. Registramos nuestro ViewSet.
# DRF creará automáticamente:
#   -> /bookings/ (para GET-list y POST-create)
#   -> /bookings/<pk>/ (para GET-retrieve, PUT-update, DELETE-destroy)
router.register(r'bookings', BookingViewSet, basename='booking')

# 3. Las URLs de la app son las del router
urlpatterns = [
    path('', include(router.urls)),
]