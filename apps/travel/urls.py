from django.urls import path
from .views import ItineraryPreviewView

urlpatterns = [
    path("preview-itinerary/", ItineraryPreviewView.as_view()),

]