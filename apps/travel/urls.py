from django.urls import path
from .views import ItineraryPreviewView
from .views import SaveItineraryView
urlpatterns = [
    path("preview-itinerary/", ItineraryPreviewView.as_view()),
    path('save-itinerary/', SaveItineraryView.as_view(), name='save-itinerary'),
]