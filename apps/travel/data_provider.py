# apps/travel/data_provider.py

import logging
from django.db.models import Q
from apps.recommendation.services import recommend_places
from apps.location.models import Place
from apps.experiences.models import ActivityService, Event
from apps.core.constants import PlaceType
from . import constants
from datetime import datetime, time, timedelta
# Imports para Favoritos
from apps.users.models import UserFavorite
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)

# --- Obtención de Actividades y Ajuste de Score ---

def _get_activity_categories(activity):
    """Extrae categorías de una actividad para matching con experiencias"""
    categories = []
    
    # Para Place y ActivityService (si tiene 'type')
    if hasattr(activity, 'type') and activity.type:
        categories.append(activity.type.lower())

    # Para ActivityService (si tiene 'category')
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

def _adjust_score_by_experiencias(activity, base_score, experiencias, user_favorites=None):
    """
    Ajusta el score de una actividad basado en Favoritos y Experiencias.
    """
    adjusted_score = base_score
    
    # 1. Bonus por Favoritos (Prioridad Alta)
    # 'service_id' es el atributo adaptado (puede ser service_id o place_id)
    if user_favorites and hasattr(activity, 'service_id') and activity.service_id in user_favorites:
        adjusted_score *= constants.FAVORITE_MATCH_BONUS

    # 2. Bonus por Experiencias
    if not experiencias:
        return min(adjusted_score, 1.0)
    
    activity_categories = _get_activity_categories(activity)
    
    for experiencia in experiencias:
        if experiencia in constants.EXPERIENCIA_TO_CATEGORIES_MAP:
            categories_for_experiencia = constants.EXPERIENCIA_TO_CATEGORIES_MAP[experiencia]
            if any(cat in activity_categories for cat in categories_for_experiencia):
                adjusted_score *= constants.EXPERIENCIA_MATCH_BONUS
                break # Solo un bonus por actividad
            
    return min(adjusted_score, 1.0)

def get_activities_with_scores(user, zone, experiencias, top_k=150):
    """
    Obtiene 'actividades' (ActivityService + Place) con sus scores, 
    ajustados por favoritos y experiencias.
    """
    try:
        # 1. Obtener ambos tipos de recomendaciones
        recommended_activities = recommend_places(user, 'activity', zone, top_k=top_k)
        recommended_places = recommend_places(user, 'place', zone, top_k=top_k)
        
        # 2. Obtener favoritos del usuario para AMBOS tipos
        user_activity_favorites = set()
        user_place_favorites = set()
        if user and user.is_authenticated:
            try:
                activity_ct = ContentType.objects.get_for_model(ActivityService)
                user_activity_favorites = set(UserFavorite.objects.filter(
                    user_id=user, content_type=activity_ct
                ).values_list('object_id', flat=True))
                
                place_ct = ContentType.objects.get_for_model(Place)
                user_place_favorites = set(UserFavorite.objects.filter(
                    user_id=user, content_type=place_ct
                ).values_list('object_id', flat=True))
                
            except Exception as e:
                logger.warning(f"Error al cargar favoritos: {e}")

        adjusted_activities = []
        service_key_map = set() # Para evitar duplicados

        # Combinar ambas listas
        all_recommendations = recommended_activities + recommended_places

        for (service, score) in all_recommendations:
            is_place = isinstance(service, Place)
            
            # 3. Adaptar el objeto para el optimizador
            if is_place:
                # Si es un Place, adaptar atributos
                service_key = service.place_id
                if service_key in service_key_map:
                    continue
                
                # Asignar atributos que el optimizador espera
                setattr(service, 'price', float(service.average_price or 0.0))
                setattr(service, 'duration_minutes', constants.DEFAULT_PLACE_DURATION_MINUTES)
                setattr(service, 'service_id', service.place_id) # Usar place_id como ID
                setattr(service, '_is_place_activity', True)
                
                favorites_set = user_place_favorites
            
            else:
                # Si es ActivityService, usar atributos existentes
                service_key = service.service_id
                if service_key in service_key_map:
                    continue
                
                # 'price' y 'duration_minutes' ya existen
                setattr(service, '_is_place_activity', False)
                favorites_set = user_activity_favorites

            service_key_map.add(service_key)

            # 4. Ajustar score
            adjusted_score = _adjust_score_by_experiencias(service, float(score), experiencias, favorites_set)
            adjusted_activities.append((service, adjusted_score))
                
        return adjusted_activities
        
    except Exception as e:
        logger.warning(f"Error getting combined activities, using fallback: {e}")
        # fallback solo usará ActivityService
        activities_qs = ActivityService.objects.all()
        if zone:
            activities_qs = activities_qs.filter(place_id__zone_id=zone)
        
        user_favorites = set()
        if user and user.is_authenticated:
             try:
                activity_content_type = ContentType.objects.get_for_model(ActivityService)
                user_favorites = set(UserFavorite.objects.filter(
                    user_id=user,
                    content_type=activity_content_type
                ).values_list('object_id', flat=True))
             except Exception:
                 pass

        result = []
        for act in activities_qs.order_by('-rating')[:top_k]:
            setattr(act, '_is_place_activity', False) # Etiquetar también en fallback
            adjusted_score = _adjust_score_by_experiencias(act, 0.5, experiencias, user_favorites)
            result.append((act, adjusted_score))
        return result

# --- Obtención de otros servicios ---

def get_accommodations(user, zone, top_k=30):
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

def get_restaurants(user, zone, top_k=60):
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

def get_events(user, zone, start_date, end_date, is_same_day, current_time, _is_night_event_func, _ensure_timezone_aware_func, _hay_solapamiento_func, top_k=45):
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