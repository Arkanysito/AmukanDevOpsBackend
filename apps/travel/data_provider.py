import logging
from django.db.models import Q
from apps.recommendation.services import recommend_places
from apps.location.models import Place
from apps.experiences.models import ActivityService, Event
from apps.core.constants import PlaceType
from . import constants
from datetime import datetime, time, timedelta

logger = logging.getLogger(__name__)

# --- Obtención de Actividades y Ajuste de Score ---

def _get_activity_categories(activity):
    """Extrae categorías de una actividad para matching con experiencias"""
    categories = []
    
    if hasattr(activity, 'category') and activity.category:
        categories.append(activity.category.lower())
    
    if hasattr(activity, 'tags'):
        if isinstance(activity.tags, list):
            categories.extend([tag.lower() for tag in activity.tags])
        elif isinstance(activity.tags, str):
            categories.extend([tag.strip().lower() for tag in activity.tags.split(',')])
            
    if hasattr(activity, 'name'):
        name_lower = activity.name.lower()
        for spanish, english in constants.KEYWORD_MAPPING.items():
            if spanish in name_lower:
                categories.append(english)
                
    return categories

def _adjust_score_by_experiencias(activity, base_score, experiencias):
    """Ajusta el score de una actividad basado en las experiencias seleccionadas"""
    if not experiencias:
        return base_score
    
    adjusted_score = base_score
    activity_categories = _get_activity_categories(activity)
    
    for experiencia in experiencias:
        if experiencia in constants.EXPERIENCIA_TO_CATEGORIES_MAP:
            categories_for_experiencia = constants.EXPERIENCIA_TO_CATEGORIES_MAP[experiencia]
            if any(cat in activity_categories for cat in categories_for_experiencia):
                adjusted_score *= constants.EXPERIENCIA_MATCH_BONUS
                break # Solo un bonus por actividad
            
    return min(adjusted_score, 1.0)

def get_activities_with_scores(user, zone, experiencias, top_k=50):
    """Obtiene actividades con sus scores de recomendación, ajustados por experiencias"""
    try:
        activities = recommend_places(user, 'activity', zone, top_k=top_k)
        
        if not activities:
            return []

        adjusted_activities = []
        
        # 'recommend_places' puede devolver lista de (servicio, score) o solo lista de servicio (fallback)
        if isinstance(activities[0], tuple):
            for activity, score in activities:
                adjusted_score = _adjust_score_by_experiencias(activity, float(score), experiencias)
                adjusted_activities.append((activity, adjusted_score))
        else:
            for activity in activities:
                adjusted_score = _adjust_score_by_experiencias(activity, 0.5, experiencias) # Score base de fallback
                adjusted_activities.append((activity, adjusted_score))
                
        return adjusted_activities
        
    except Exception as e:
        logger.warning(f"Error getting activities from recommendation service, using fallback: {e}")
        activities_qs = ActivityService.objects.all()
        if zone:
            activities_qs = activities_qs.filter(place_id__zone_id=zone)
        
        result = []
        for act in activities_qs[:top_k]:
            adjusted_score = _adjust_score_by_experiencias(act, 0.5, experiencias)
            result.append((act, adjusted_score))
        return result

# --- Obtención de otros servicios ---

def get_accommodations(user, zone, top_k=10):
    """Obtiene alojamientos DESDE PLACE"""
    try:
        accommodations = recommend_places(user, 'accommodation', zone, top_k=top_k)
        if accommodations and isinstance(accommodations[0], tuple):
            return [acc for acc, score in accommodations]
        return accommodations
    except Exception as e:
        logger.warning(f"Error getting accommodations from recommendation service, using fallback: {e}")
        interesting_types = [pt.value for pt in constants.ACCOMMODATION_TYPES]
        accommodations_qs = Place.objects.filter(type__in=interesting_types)
        if zone:
            accommodations_qs = accommodations_qs.filter(zone_id=zone)
        return list(accommodations_qs.order_by('-rating')[:top_k])

def get_restaurants(user, zone, top_k=20):
    """Obtiene restaurantes DESDE PLACE"""
    try:
        restaurants = recommend_places(user, 'restaurant', zone, top_k=top_k)
        if restaurants and isinstance(restaurants[0], tuple):
            return [rest for rest, score in restaurants]
        return restaurants
    except Exception as e:
        logger.warning(f"Error getting restaurants from recommendation service, using fallback: {e}")
        interesting_types = [pt.value for pt in constants.RESTAURANT_TYPES]
        restaurants_qs = Place.objects.filter(type__in=interesting_types)
        if zone:
            restaurants_qs = restaurants_qs.filter(zone_id=zone)
        return list(restaurants_qs.order_by('-rating')[:top_k])

def get_events(user, zone, start_date, end_date, is_same_day, current_time, _is_night_event_func, _ensure_timezone_aware_func, _hay_solapamiento_func, top_k=15):
    """Obtiene eventos incluyendo eventos nocturnos."""
    try:
        events = recommend_places(user, 'event', zone, top_k=top_k)
        if events and isinstance(events[0], tuple):
            events = [event for event, score in events]
        
        filtered_events = []
        for event in events:
            event_start = _ensure_timezone_aware_func(event.start_date)
            event_end = _ensure_timezone_aware_func(event.end_date)
            
            if is_same_day:
                if event_end < current_time:
                    continue
                if event_start < current_time < event_end:
                    event_start = current_time
                
                # Chequear si es hoy o cruza a mañana (madrugada)
                if event_start.date() == start_date.date() or \
                   (event_end.date() == start_date.date() + timedelta(days=1) and event_end.hour < 6):
                    filtered_events.append(event)
            else:
                extended_end = end_date + timedelta(hours=6)
                if _hay_solapamiento_func(event_start, event_end, start_date, extended_end):
                    filtered_events.append(event)
                    
        return filtered_events[:top_k]
        
    except Exception as e:
        logger.warning(f"Error getting events from recommendation service, using fallback: {e}")
        events_qs = Event.objects.filter(
            Q(start_date__lte=end_date + timedelta(hours=6)) &
            Q(end_date__gte=start_date)
        )
        if is_same_day:
            events_qs = events_qs.filter(end_date__gte=current_time)
        if zone:
            events_qs = events_qs.filter(place_id__zone_id=zone)
        return list(events_qs.order_by('start_date')[:top_k])