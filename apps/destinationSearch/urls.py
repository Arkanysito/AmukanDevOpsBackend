from django.urls import path
from .views.accommodations import AccommodationListView
from .views.activities import ActivityListView
from .views.events import EventListView
from .views.search import SearchAllView

urlpatterns = [
    path('accommodations/', AccommodationListView.as_view()),
    path('activities/', ActivityListView.as_view()),
    path('events/', EventListView.as_view()),
    path('search/', SearchAllView.as_view()),
]