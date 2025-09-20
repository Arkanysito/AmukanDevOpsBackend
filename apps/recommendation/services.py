import numpy as np
from django.db.models import Prefetch, Q
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from datetime import timedelta
import random

from apps.users.models import CustomUser, UserInterest
from apps.location.models import Place, Zone
from apps.experiences.models import AccommodationService, ActivityService, TransportService, Event
from apps.core.constants import PlaceType, InteractionAction
from apps.tracking.models import Interaction

def get_user_vector(user: CustomUser) -> np.ndarray:
    """Construye vector de usuario promediando embeddings de sus intereses."""
    interests = UserInterest.objects.filter(user_id=user.id)\
                  .select_related("interest_id")
    
    if not interests:
        return None
    
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    interest_embeddings = []
    for interest in interests:
        text = interest.interest_id.name
        emb = model.encode(text)
        weighted_emb = emb * float(interest.weight)
        interest_embeddings.append(weighted_emb)
    
    user_embedding = np.mean(interest_embeddings, axis=0)
    return user_embedding

def recommend_places(user: CustomUser, service_type: str, zone: Zone = None, top_k: int = 20):
    """
    Recomienda servicios basados en los intereses del usuario.
    
    Args:
        user: Usuario para el cual generar recomendaciones
        service_type: Tipo de servicio ('accommodation', 'activity', 'transport', 'event', 'place')
        zone: Zona geográfica para filtrar (opcional)
        top_k: Número máximo de recomendaciones
    
    Returns:
        Lista de servicios con sus scores de similitud
    """
    try:
        u_vec = get_user_vector(user)
        
        # Si no hay vector de usuario, usar recomendaciones por rating
        if u_vec is None or u_vec.size == 0:
            return get_fallback_services(service_type, zone, top_k)
        
        # Obtener servicios según el tipo
        if service_type == 'accommodation':
            services = AccommodationService.objects.exclude(embedding=None)
            if zone:
                services = services.filter(place_id__zone_id=zone)
        elif service_type == 'activity':
            services = ActivityService.objects.exclude(embedding=None)
            if zone:
                services = services.filter(place_id__zone_id=zone)
        elif service_type == 'event':
            services = Event.objects.exclude(embedding=None)
            if zone:
                services = services.filter(place_id__zone_id=zone)
        elif service_type == 'restaurant':
            categories = [
                PlaceType.RESTAURANT, PlaceType.CAFE, PlaceType.BAR, PlaceType.PUB,
            ]
            interesting_types = [pt.value for pt in categories]
            services = Place.objects.exclude(embedding=None).filter(type__in=interesting_types)
            if zone:
                services = services.filter(zone_id=zone)
        elif service_type == 'place':
            interesting_categories = [
                PlaceType.ATTRACTION, PlaceType.VIEWPOINT, PlaceType.BEACH, PlaceType.PARK,
                PlaceType.MUSEUM, PlaceType.GALLERY, PlaceType.ART_GALLERY, PlaceType.HISTORIC_SITE,
                PlaceType.MONUMENT, PlaceType.CASTLE, PlaceType.THEATRE, PlaceType.CINEMA,
                PlaceType.CONCERT_HALL, PlaceType.SPORTS_CENTRE, PlaceType.STADIUM,
                PlaceType.NIGHTCLUB, PlaceType.SHOPPING_MALL, PlaceType.MARKET,
                PlaceType.ZOO, PlaceType.AQUARIUM, PlaceType.BOTANICAL_GARDEN,
                PlaceType.HOT_SPRING, PlaceType.SKI_RESORT, PlaceType.ADVENTURE_PARK,
                PlaceType.BOOKS, PlaceType.LIBRARY,
            ]
            interesting_types = [pt.value for pt in interesting_categories]
            services = Place.objects.exclude(embedding=None).filter(type__in=interesting_types)
            if zone:
                services = services.filter(zone_id=zone)
        else:
            return []
        
        # Si no hay suficientes servicios, usar fallback
        if services.count() < top_k:
            fallback_services = get_fallback_services(service_type, zone, top_k - services.count())
            results = [(s, 0.5) for s in services] + [(s, 0.5) for s in fallback_services]
            return results[:top_k]
        
        # Calcular similitud para cada servicio
        results = []
        for service in services:
            if service.embedding is None:
                continue
                
            if isinstance(service.embedding, np.ndarray):
                embedding_data = service.embedding.tolist()
            else:
                embedding_data = service.embedding
                
            if not isinstance(embedding_data, list) or len(embedding_data) == 0:
                continue
                
            service_embedding = np.array(embedding_data, dtype=np.float32)
            score = cosine_similarity([u_vec], [service_embedding])[0][0]
            results.append((service, score))
        
        # Ordenar por score y retornar los mejores
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
        
    except Exception as e:
        print(f"Error in recommend_places: {e}")
        return get_fallback_services(service_type, zone, top_k)

def get_fallback_services(service_type: str, zone: Zone = None, top_k: int = 10):
    """Recomendaciones de fallback: servicios bien evaluados"""
    if service_type == 'accommodation':
        services = AccommodationService.objects.all()
        if zone:
            services = services.filter(place_id__zone_id=zone)
        return list(services.order_by('-rating')[:top_k])
    elif service_type == 'activity':
        services = ActivityService.objects.all()
        if zone:
            services = services.filter(place_id__zone_id=zone)
        return list(services.order_by('-rating')[:top_k])
    elif service_type == 'event':
        services = Event.objects.all()
        if zone:
            services = services.filter(place_id__zone_id=zone)
        return list(services.order_by('-rating')[:top_k])
    elif service_type == 'place':
        interesting_types = [
            'restaurant', 'cafe', 'attraction', 'viewpoint', 'beach', 'park', 
            'museum', 'gallery', 'cinema', 'theatre'
        ]
        services = Place.objects.filter(type__in=interesting_types)
        if zone:
            services = services.filter(zone_id=zone)
        return list(services.order_by('-rating')[:top_k])
    else:
        return []