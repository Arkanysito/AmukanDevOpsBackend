from apps.experiences.models import Event, AccommodationService, ActivityService
from django.db.models import Q

def filter_events(budget=None, start_date=None, end_date=None):
    querys = Event.objects.all()
    if budget:
        querys = querys.filter(price__lte=budget)
    if start_date and end_date:
        querys = querys.filter(
        Q(start_date__range=(start_date, end_date)) |  # empieza dentro del rango
        Q(end_date__range=(start_date, end_date)) |    # termina dentro del rango
        Q(start_date__lte=start_date, end_date__gte=end_date)  # cubre todo el rango
        )
    return querys

def filter_accommodations(budget=None, travelers=None):
    querys = AccommodationService.objects.all()
    if budget:
        querys = querys.filter(price__lte=budget)
    if travelers:
        querys = querys.filter(room_capacity__gte=travelers)
    return querys

def filter_activities(budget=None):
    querys = ActivityService.objects.all()
    if budget:
        querys = querys.filter(price__lte=budget)
    return querys