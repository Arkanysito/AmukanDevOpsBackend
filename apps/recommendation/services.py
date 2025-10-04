import numpy as np
from django.db.models import Prefetch, Q
from django.core.cache import cache
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from datetime import timedelta
from functools import lru_cache
import hashlib
import pickle
import random

from apps.users.models import CustomUser, UserInterest
from apps.location.models import Place, Zone
from apps.experiences.models import AccommodationService, ActivityService, TransportService, Event
from apps.core.constants import PlaceType, InteractionAction
from apps.tracking.models import Interaction

# ============================================================================
# Singleton para el modelo - Carga UNA SOLA VEZ
# ============================================================================
class ModelSingleton:
    """Singleton para mantener el modelo en memoria y evitar recargas"""
    _instance = None
    _model = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelSingleton, cls).__new__(cls)
            cls._model = None
        return cls._instance
    
    def get_model(self):
        """Retorna el modelo, cargándolo solo si es necesario"""
        if self._model is None:
            print("Loading SentenceTransformer model (one-time operation)...")
            self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            print("Model loaded successfully")
        return self._model

# Instancia global
_model_singleton = ModelSingleton()

def get_sentence_transformer():
    """Función helper para obtener el modelo"""
    return _model_singleton.get_model()


# ============================================================================
# Cache de vectores de usuario con Django Cache
# ============================================================================
def get_user_vector_cache_key(user_id: int) -> str:
    """Genera clave de cache para el vector de usuario"""
    return f"user_vector_{user_id}"

def invalidate_user_vector_cache(user_id: int):
    """Invalida el cache cuando cambian los intereses del usuario"""
    cache_key = get_user_vector_cache_key(user_id)
    cache.delete(cache_key)

def get_user_vector(user: CustomUser, use_cache: bool = True) -> np.ndarray:
    """
    Construye vector de usuario con cache
    """
    if user is None:
        return None
    
    # Intentar obtener del cache
    if use_cache:
        cache_key = get_user_vector_cache_key(user.id)
        cached_vector = cache.get(cache_key)
        if cached_vector is not None:
            return cached_vector
    
    # Optimización: select_related para evitar N+1 queries
    interests = UserInterest.objects.filter(user_id=user.id)\
                  .select_related("interest_id")\
                  .only('interest_id__name', 'weight')
    
    if not interests:
        return None
    
    # Usar singleton del modelo
    model = get_sentence_transformer()
    
    # Procesar embeddings
    interest_embeddings = []
    for interest in interests:
        text = interest.interest_id.name
        emb = model.encode(text, show_progress_bar=False)
        weighted_emb = emb * float(interest.weight)
        interest_embeddings.append(weighted_emb)
    
    user_embedding = np.mean(interest_embeddings, axis=0)
    
    # Guardar en cache (24 horas por defecto)
    if use_cache:
        cache_key = get_user_vector_cache_key(user.id)
        cache.set(cache_key, user_embedding, timeout=86400)
    
    return user_embedding


# ============================================================================
# FUNCIÓN HELPER: Obtener clave única del servicio
# ============================================================================
def get_service_key(service):
    """Obtiene la clave única para un servicio basado en su tipo"""
    if hasattr(service, 'service_id'):
        return service.service_id  # AccommodationService, ActivityService
    elif hasattr(service, 'event_id'):
        return service.event_id    # Event
    elif hasattr(service, 'place_id'):
        return service.place_id    # Place
    else:
        return getattr(service, 'id', None)


# ============================================================================
# MEJORA 3: Batch processing de embeddings de servicios
# ============================================================================
def get_service_embeddings_batch(services):
    """
    Procesa embeddings en batch para mejor eficiencia.
    """
    embeddings_map = {}
    
    for service in services:
        if service.embedding is None:
            continue
        
        try:
            # Usar función helper para obtener clave consistente
            service_key = get_service_key(service)
            
            if service_key is None:
                continue
                
            if isinstance(service.embedding, np.ndarray):
                embedding_data = service.embedding.tolist()
            else:
                embedding_data = service.embedding
            
            if not isinstance(embedding_data, list) or len(embedding_data) == 0:
                continue
            
            service_embedding = np.array(embedding_data, dtype=np.float32)
            embeddings_map[service_key] = service_embedding
        except Exception as e:
            print(f"Error processing embedding for service {get_service_key(service)}: {e}")
            continue
    
    return embeddings_map


# ============================================================================
# MEJORA 4: Optimización de queries con prefetch y select_related
# ============================================================================
def get_optimized_services_queryset(service_type: str, zone: Zone = None):
    """
    Retorna queryset optimizado según el tipo de servicio.
    """
    if service_type == 'accommodation':
        base_fields = ['service_id', 'embedding', 'rating', 'price']
        queryset = AccommodationService.objects.exclude(embedding=None)\
            .select_related('place_id')\
            .only(*base_fields, 'place_id__zone_id', 'place_id__name')
        
        if zone:
            queryset = queryset.filter(place_id__zone_id=zone)
            
    elif service_type == 'activity':
        base_fields = ['service_id', 'embedding', 'rating', 'price']
        queryset = ActivityService.objects.exclude(embedding=None)\
            .select_related('place_id')\
            .only(*base_fields, 'place_id__zone_id', 'place_id__name', 'duration_minutes')
        
        if zone:
            queryset = queryset.filter(place_id__zone_id=zone)
            
    elif service_type == 'event':
        base_fields = ['event_id', 'embedding', 'rating', 'price']
        queryset = Event.objects.exclude(embedding=None)\
            .select_related('place_id')\
            .only(*base_fields, 'place_id__zone_id', 'start_date', 'end_date')
        
        if zone:
            queryset = queryset.filter(place_id__zone_id=zone)
            
    elif service_type == 'restaurant':
        categories = [
            PlaceType.RESTAURANT, PlaceType.CAFE, PlaceType.BAR, PlaceType.PUB,
        ]
        interesting_types = [pt.value for pt in categories]
        
        base_fields = ['place_id', 'embedding', 'rating']
        queryset = Place.objects.exclude(embedding=None)\
            .filter(type__in=interesting_types)\
            .only(*base_fields, 'zone_id', 'name', 'type')
        
        if zone:
            queryset = queryset.filter(zone_id=zone)
            
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
        
        base_fields = ['place_id', 'embedding', 'rating']
        queryset = Place.objects.exclude(embedding=None)\
            .filter(type__in=interesting_types)\
            .only(*base_fields, 'zone_id', 'name', 'type')
        
        if zone:
            queryset = queryset.filter(zone_id=zone)
    else:
        return None
    
    return queryset


# ============================================================================
# Cache de recomendaciones completas
# ============================================================================
def get_recommendations_cache_key(user_id: int, service_type: str, zone_id: int = None, top_k: int = 20) -> str:
    """Genera clave de cache para recomendaciones completas"""
    zone_str = str(zone_id) if zone_id else "all"
    return f"recommendations_{user_id}_{service_type}_{zone_str}_{top_k}"

def recommend_places(user: CustomUser, service_type: str, zone: Zone = None, 
                    top_k: int = 20, use_cache: bool = True):
    """
    Recomienda servicios con optimizaciones de rendimiento.
    """
    try:
        # Cache de recomendaciones completas
        if use_cache and user is not None:
            cache_key = get_recommendations_cache_key(
                user.id, service_type, zone.zone_id if zone else None, top_k
            )
            cached_recommendations = cache.get(cache_key)
            if cached_recommendations is not None:
                return cached_recommendations
        
        # Obtener vector de usuario con cache
        u_vec = get_user_vector(user, use_cache=use_cache)
        
        # Fallback si no hay vector
        if u_vec is None or u_vec.size == 0:
            fallback = get_fallback_services(service_type, zone, top_k)
            return [(s, 0.5) for s in fallback]
        
        # Obtener servicios con query optimizada
        services = get_optimized_services_queryset(service_type, zone)
        
        if services is None:
            return []
        
        # Evaluar count para decidir estrategia
        services_count = services.count()
        
        if services_count == 0:
            fallback = get_fallback_services(service_type, zone, top_k)
            return [(s, 0.5) for s in fallback]
        
        # Si hay pocos servicios, combinar con fallback
        if services_count < top_k:
            services_list = list(services)
            embeddings_map = get_service_embeddings_batch(services_list)
            
            results = []
            for service in services_list:
                service_key = get_service_key(service)
                if service_key in embeddings_map:
                    service_embedding = embeddings_map[service_key]
                    score = cosine_similarity([u_vec], [service_embedding])[0][0]
                    results.append((service, float(score)))
            
            # Agregar fallback si es necesario
            if len(results) < top_k:
                fallback_count = top_k - len(results)
                fallback_services = get_fallback_services(service_type, zone, fallback_count)
                results.extend([(s, 0.5) for s in fallback_services])
            
            results.sort(key=lambda x: x[1], reverse=True)
            final_results = results[:top_k]
            
            # Cachear resultados (5 minutos)
            if use_cache and user is not None:
                cache_key = get_recommendations_cache_key(
                    user.id, service_type, zone.zone_id if zone else None, top_k
                )
                cache.set(cache_key, final_results, timeout=300)
            
            return final_results
        
        # Procesar todos los servicios
        services_list = list(services[:top_k * 3])
        embeddings_map = get_service_embeddings_batch(services_list)
        
        # Calcular similitudes en batch
        results = []
        for service in services_list:
            service_key = get_service_key(service)
            if service_key not in embeddings_map:
                continue
            
            service_embedding = embeddings_map[service_key]
            score = cosine_similarity([u_vec], [service_embedding])[0][0]
            results.append((service, float(score)))
        
        # Ordenar y retornar top_k
        results.sort(key=lambda x: x[1], reverse=True)
        final_results = results[:top_k]
        
        # Cachear resultados (5 minutos)
        if use_cache and user is not None:
            cache_key = get_recommendations_cache_key(
                user.id, service_type, zone.zone_id if zone else None, top_k
            )
            cache.set(cache_key, final_results, timeout=300)
        
        return final_results
        
    except Exception as e:
        print(f"Error in recommend_places: {e}")
        fallback = get_fallback_services(service_type, zone, top_k)
        return [(s, 0.5) for s in fallback]


# ============================================================================
# Fallback optimizado con cache de queries
# ============================================================================
def get_fallback_services(service_type: str, zone: Zone = None, top_k: int = 10):
    """
    Recomendaciones de fallback optimizadas.
    """
    cache_key = f"fallback_{service_type}_{zone.zone_id if zone else 'all'}_{top_k}"
    
    # Intentar obtener del cache (cache corto: 2 minutos)
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    if service_type == 'accommodation':
        services = AccommodationService.objects.all()\
            .select_related('place_id')\
            .only('service_id', 'rating', 'price', 'place_id__name')
        
        if zone:
            services = services.filter(place_id__zone_id=zone)
        
        result = list(services.order_by('-rating')[:top_k])
        
    elif service_type == 'activity':
        services = ActivityService.objects.all()\
            .select_related('place_id')\
            .only('service_id', 'rating', 'price', 'duration_minutes', 'place_id__name')
        
        if zone:
            services = services.filter(place_id__zone_id=zone)
        
        result = list(services.order_by('-rating')[:top_k])
        
    elif service_type == 'event':
        services = Event.objects.all()\
            .select_related('place_id')\
            .only('event_id', 'rating', 'price', 'start_date', 'end_date', 'place_id__name')
        
        if zone:
            services = services.filter(place_id__zone_id=zone)
        
        result = list(services.order_by('-rating')[:top_k])
        
    elif service_type in ['place', 'restaurant']:
        interesting_types = [
            'restaurant', 'cafe', 'attraction', 'viewpoint', 'beach', 'park', 
            'museum', 'gallery', 'cinema', 'theatre'
        ]
        
        services = Place.objects.filter(type__in=interesting_types)\
            .only('place_id', 'rating', 'name', 'type', 'zone_id')
        
        if zone:
            services = services.filter(zone_id=zone)
        
        result = list(services.order_by('-rating')[:top_k])
    else:
        result = []
    
    # Cachear resultado (2 minutos)
    cache.set(cache_key, result, timeout=120)
    
    return result


# ============================================================================
# Función para precarga de modelos
# ============================================================================
def warmup_recommendation_system():
    """
    Precarga el modelo en memoria durante el startup de Django.
    """
    try:
        print("Warming up recommendation system...")
        model = get_sentence_transformer()
        # Test encoding
        _ = model.encode("test", show_progress_bar=False)
        print("Recommendation system ready")
    except Exception as e:
        print(f"Warning: Could not warm up recommendation system: {e}")


# ============================================================================
# Herramienta de monitoreo de cache
# ============================================================================
class RecommendationCacheMonitor:
    """Monitor para estadísticas de cache del sistema de recomendaciones"""
    
    @staticmethod
    def get_cache_stats():
        """Retorna estadísticas de uso de cache"""
        try:
            from django.core.cache import cache as django_cache
            
            if hasattr(django_cache, 'get_stats'):
                return django_cache.get_stats()
            else:
                return {
                    'status': 'Cache backend does not support stats',
                    'backend': str(type(django_cache))
                }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def clear_all_recommendation_caches():
        """Limpia todos los caches de recomendaciones"""
        from django.core.cache import cache as django_cache
        
        patterns = [
            'user_vector_*',
            'recommendations_*',
            'fallback_*'
        ]
        
        cleared_count = 0
        
        if hasattr(django_cache, 'delete_pattern'):
            for pattern in patterns:
                try:
                    django_cache.delete_pattern(pattern)
                    cleared_count += 1
                except Exception as e:
                    print(f"Error clearing pattern {pattern}: {e}")
        
        return {
            'cleared_patterns': cleared_count,
            'message': 'Cache clearing completed' if cleared_count > 0 else 'Cache backend does not support pattern deletion'
        }


# ============================================================================
# Batch recommendations para múltiples usuarios
# ============================================================================
def recommend_places_batch(users: list, service_type: str, zone: Zone = None, top_k: int = 20):
    """
    Genera recomendaciones para múltiples usuarios en batch.
    """
    results = {}
    
    # Precalcular vectores de usuarios
    user_vectors = {}
    for user in users:
        u_vec = get_user_vector(user, use_cache=True)
        if u_vec is not None:
            user_vectors[user.id] = u_vec
    
    # Cargar servicios una sola vez
    services = get_optimized_services_queryset(service_type, zone)
    if services is None:
        return results
    
    services_list = list(services[:top_k * 3])
    embeddings_map = get_service_embeddings_batch(services_list)
    
    # Calcular recomendaciones para cada usuario
    for user in users:
        if user.id not in user_vectors:
            results[user.id] = get_fallback_services(service_type, zone, top_k)
            continue
        
        u_vec = user_vectors[user.id]
        recommendations = []
        
        for service in services_list:
            service_key = get_service_key(service)
            if service_key not in embeddings_map:
                continue
            
            service_embedding = embeddings_map[service_key]
            score = cosine_similarity([u_vec], [service_embedding])[0][0]
            recommendations.append((service, float(score)))
        
        recommendations.sort(key=lambda x: x[1], reverse=True)
        results[user.id] = recommendations[:top_k]
        
        # Cachear cada resultado
        cache_key = get_recommendations_cache_key(
            user.id, service_type, zone.zone_id if zone else None, top_k
        )
        cache.set(cache_key, results[user.id], timeout=300)
    
    return results