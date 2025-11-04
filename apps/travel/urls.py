from django.urls import path
from .views import DebugItineraryView, ItineraryPreviewView, SaveItineraryView, UserItinerariesView, ItineraryDetailView

urlpatterns = [
    path("preview-itinerary/", ItineraryPreviewView.as_view(), name='preview-itinerary'),
    path('save-itinerary/', SaveItineraryView.as_view(), name='save-itinerary'),
    path('my-itineraries/', UserItinerariesView.as_view(), name='my-itineraries'),
    path('itinerary/<uuid:itinerary_id>/', ItineraryDetailView.as_view(), name='itinerary-detail'),
    path('debug-itinerary/<uuid:itinerary_id>/', DebugItineraryView.as_view(), name='debug-itinerary'),
]