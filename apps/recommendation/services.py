# apps/recommendation/services.py

import numpy as np
from django.core.cache import cache
from apps.users.models import CustomUser, UserInterest
from apps.location.models import Place, Zone
from apps.experiences.models import ActivityService, Event
from apps.core.constants import PlaceType
from .ml_model import encode_texts, get_transformer_model

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
    
    # Procesar embeddings con transformers
    interest_texts = [interest.interest_id.name for interest in interests]
    interest_embeddings = encode_texts(interest_texts)
    
    # Aplicar pesos
    weighted_embeddings = []
    for i, interest in enumerate(interests):
        weighted_emb = interest_embeddings[i] * float(interest.weight)
        weighted_embeddings.append(weighted_emb)
    
    user_embedding = np.mean(weighted_embeddings, axis=0)
    
    # NORMALIZAR EL VECTOR DEL USUARIO (ARREGLA LAS SIMILITUDES BAJAS)
    user_norm = np.linalg.norm(user_embedding)
    if user_norm > 0:
        user_embedding = user_embedding / user_norm
    
    # Guardar en cache
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
# Batch processing de embeddings de servicios
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
# Optimización de queries con prefetch y select_related
# ============================================================================
def get_optimized_services_queryset(service_type: str, zone: Zone = None):
    """
    Retorna queryset optimizado según el tipo de servicio.
    """
    if service_type == 'accommodation':
        # CAMBIO PRINCIPAL: Ahora usamos Place en lugar de AccommodationService
        accommodation_types = [
            PlaceType.HOTEL, PlaceType.HOSTEL, PlaceType.GUEST_HOUSE, 
            PlaceType.APARTMENT, PlaceType.RESORT, PlaceType.BED_BREAKFAST,
            PlaceType.MOTEL, PlaceType.CAMPSITE
        ]
        interesting_types = [pt.value for pt in accommodation_types]
        
        base_fields = ['place_id', 'embedding', 'rating', 'average_price']
        queryset = Place.objects.exclude(embedding=None)\
            .filter(type__in=interesting_types)\
            .only(*base_fields, 'zone_id', 'name', 'type')
        
        if zone:
            queryset = queryset.filter(zone_id=zone)
            
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
        # Lista expandida de PlaceType que pueden considerarse "actividades"
        interesting_categories = [
            PlaceType.PARK, PlaceType.MUSEUM, PlaceType.BEACH, PlaceType.VIEWPOINT,
            PlaceType.LIBRARY, PlaceType.CINEMA, PlaceType.THEATRE, PlaceType.STADIUM,
            PlaceType.SPORTS_CENTRE, PlaceType.MARKETPLACE, PlaceType.SHOP, PlaceType.MALL,
            PlaceType.ZOO, PlaceType.AQUARIUM, PlaceType.NIGHTCLUB, PlaceType.ATTRACTION,
            PlaceType.ARTWORK, PlaceType.GALLERY, PlaceType.THEME_PARK, PlaceType.GARDEN,
            PlaceType.SWIMMING_POOL, PlaceType.GOLF_COURSE, PlaceType.FITNESS_CENTRE,
            PlaceType.PLAYGROUND, PlaceType.MONUMENT, PlaceType.MEMORIAL, PlaceType.CASTLE,
            PlaceType.RUINS, PlaceType.ARCHAEOLOGICAL_SITE, PlaceType.BOOKS,
            PlaceType.CONCERT_HALL, PlaceType.BOTANICAL_GARDEN, PlaceType.HOT_SPRING,
            PlaceType.SKI_RESORT, PlaceType.ADVENTURE_PARK, PlaceType.ART_GALLERY,
            PlaceType.HISTORIC_SITE, PlaceType.SHOPPING_MALL, PlaceType.MARKET,
        ]
        
        interesting_types = [pt.value for pt in interesting_categories]
        
        base_fields = ['place_id', 'embedding', 'rating', 'average_price'] # Añadido average_price
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

import numpy as np

def cosine_similarity_numpy(vec1, vec2):
    """Calcula similitud coseno entre dos vectores usando numpy"""
    vec1_array = np.array(vec1, dtype=np.float32)
    vec2_array = np.array(vec2, dtype=np.float32)
    
    dot_product = np.dot(vec1_array, vec2_array)
    norm1 = np.linalg.norm(vec1_array)
    norm2 = np.linalg.norm(vec2_array)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)

def recommend_places(user: CustomUser, service_type: str, zone: Zone = None, 
                     top_k: int = 20, use_cache: bool = True, diversity_ratio: float = 0.3):
    """
    Recomienda servicios con diversificación para evitar sobre-especialización.
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
        
        # Si hay pocos servicios, no aplicar diversificación
        if services_count < top_k * 1.5:
            services_list = list(services)
            embeddings_map = get_service_embeddings_batch(services_list)
            
            results = []
            for service in services_list:
                service_key = get_service_key(service)
                if service_key in embeddings_map:
                    service_embedding = embeddings_map[service_key]
                    score = cosine_similarity_numpy(u_vec, service_embedding)
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
        
        # ESTRATEGIA CON DIVERSIFICACIÓN - Para cuando hay suficientes servicios
        
        # Obtener más servicios para permitir diversificación
        services_list = list(services[:top_k * 5])  # Más servicios para seleccionar
        embeddings_map = get_service_embeddings_batch(services_list)
        
        # Calcular similitudes para todos los servicios
        results = []
        for service in services_list:
            service_key = get_service_key(service)
            if service_key not in embeddings_map:
                continue
            
            service_embedding = embeddings_map[service_key]
            score = cosine_similarity_numpy(u_vec, service_embedding)
            results.append((service, float(score)))
        
        # Ordenar por similitud
        results.sort(key=lambda x: x[1], reverse=True)
        
        # APLICAR DIVERSIFICACIÓN
        final_results = _diversify_recommendations(results, top_k, diversity_ratio)
        
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


def _diversify_recommendations(recommendations, top_k, diversity_ratio=0.3):
    """
    Diversifica las recomendaciones mezclando servicios similares y diversos.
    
    Args:
        recommendations: Lista de (servicio, score) ordenada por score
        top_k: Número total de recomendaciones a retornar
        diversity_ratio: Proporción de recomendaciones diversas (0.0-1.0)
    """
    if len(recommendations) <= top_k:
        return recommendations[:top_k]
    
    # Calcular cuántas recomendaciones diversas incluir
    num_diverse = max(1, int(top_k * diversity_ratio))
    num_main = top_k - num_diverse
    
    # Tomar las mejores recomendaciones (alta similitud)
    main_recommendations = recommendations[:num_main * 2]  # Tomar el doble para seleccionar
    
    # Seleccionar recomendaciones diversas (de la parte media)
    diverse_candidates = recommendations[num_main * 2:num_main * 2 + num_diverse * 3]
    
    # Estrategia de diversificación: mezclar por tipo/categoría
    final_results = []
    
    # 1. Agregar las mejores recomendaciones (asegurar relevancia)
    final_results.extend(main_recommendations[:num_main])
    
    # 2. Agregar recomendaciones diversas
    if diverse_candidates:
        # Seleccionar diversos intentando variar tipos/categorías
        selected_diverse = _select_diverse_services(diverse_candidates, num_diverse)
        final_results.extend(selected_diverse)
    
    # Si no conseguimos suficientes, completar con las siguientes mejores
    if len(final_results) < top_k:
        remaining = top_k - len(final_results)
        # Tomar de las que no están ya seleccionadas
        all_selected_ids = {service[0].place_id for service in final_results if hasattr(service[0], 'place_id')}
        additional = [rec for rec in recommendations if get_service_key(rec[0]) not in all_selected_ids]
        final_results.extend(additional[:remaining])
    
    return final_results[:top_k]


def _select_diverse_services(candidates, num_to_select):
    """
    Selecciona servicios diversos basándose en tipos/categorías.
    """
    if not candidates or num_to_select <= 0:
        return []
    
    selected = []
    selected_types = set()
    
    for service, score in candidates:
        if len(selected) >= num_to_select:
            break
        
        # Obtener tipo/categoría del servicio
        service_type = _get_service_category(service)
        
        # Si es un tipo nuevo, agregarlo para diversidad
        if service_type not in selected_types:
            selected.append((service, score))
            selected_types.add(service_type)
    
    # Si no conseguimos suficientes tipos diversos, completar con los restantes
    if len(selected) < num_to_select:
        remaining = num_to_select - len(selected)
        # Agregar los que no están ya seleccionados
        selected_ids = {get_service_key(service) for service, score in selected}
        additional = [candidate for candidate in candidates if get_service_key(candidate[0]) not in selected_ids]
        selected.extend(additional[:remaining])
    
    return selected


def _get_service_category(service):
    """
    Obtiene una categoría para el servicio para diversificación.
    """
    # Priorizar tipo específico
    if hasattr(service, 'type'):
        return getattr(service, 'type', 'unknown')
    
    # Para ActivityService, usar categoría
    if hasattr(service, 'category'):
        return getattr(service, 'category', 'unknown')
    
    # Para Event, usar categoría o tipo
    if hasattr(service, 'category'):
        return getattr(service, 'category', 'unknown')
    
    # Fallback: usar clase del modelo
    return service.__class__.__name__


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
        accommodation_types = [
            PlaceType.HOTEL, PlaceType.HOSTEL, PlaceType.GUEST_HOUSE, 
            PlaceType.RESORT, PlaceType.BED_BREAKFAST, PlaceType.MOTEL
        ]
        interesting_types = [pt.value for pt in accommodation_types]
        
        services = Place.objects.filter(type__in=interesting_types)\
            .only('place_id', 'rating', 'average_price', 'name', 'type', 'zone_id')
        
        if zone:
            services = services.filter(zone_id=zone)
        
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
         
    elif service_type == 'restaurant':
        interesting_types = [
            PlaceType.RESTAURANT, PlaceType.CAFE, PlaceType.BAR, PlaceType.PUB,
        ]
        interesting_types_values = [pt.value for pt in interesting_types]
        
        services = Place.objects.filter(type__in=interesting_types_values)\
            .only('place_id', 'rating', 'name', 'type', 'zone_id')
        
        if zone:
            services = services.filter(zone_id=zone)
            
        result = list(services.order_by('-rating')[:top_k])

    elif service_type == 'place':
        interesting_categories = [
            PlaceType.PARK, PlaceType.MUSEUM, PlaceType.BEACH, PlaceType.VIEWPOINT,
            PlaceType.LIBRARY, PlaceType.CINEMA, PlaceType.THEATRE, PlaceType.STADIUM,
            PlaceType.SPORTS_CENTRE, PlaceType.MARKETPLACE, PlaceType.SHOP, PlaceType.MALL,
            PlaceType.ZOO, PlaceType.AQUARIUM, PlaceType.NIGHTCLUB, PlaceType.ATTRACTION,
            PlaceType.ARTWORK, PlaceType.GALLERY, PlaceType.THEME_PARK, PlaceType.GARDEN,
            PlaceType.SWIMMING_POOL, PlaceType.GOLF_COURSE, PlaceType.FITNESS_CENTRE,
            PlaceType.PLAYGROUND, PlaceType.MONUMENT, PlaceType.MEMORIAL, PlaceType.CASTLE,
            PlaceType.RUINS, PlaceType.ARCHAEOLOGICAL_SITE, PlaceType.BOOKS,
            PlaceType.CONCERT_HALL, PlaceType.BOTANICAL_GARDEN, PlaceType.HOT_SPRING,
            PlaceType.SKI_RESORT, PlaceType.ADVENTURE_PARK, PlaceType.ART_GALLERY,
            PlaceType.HISTORIC_SITE, PlaceType.SHOPPING_MALL, PlaceType.MARKET,
        ]
        interesting_types = [pt.value for pt in interesting_categories]
        
        services = Place.objects.filter(type__in=interesting_types)\
            .only('place_id', 'rating', 'name', 'type', 'zone_id', 'average_price')
        
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
        model, tokenizer = get_transformer_model()
        # Test encoding
        _ = encode_texts("test")
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
    Versión optimizada para batch usando operaciones vectorizadas.
    """
    results = {}
    
    # Precalcular vectores de usuarios
    user_vectors = {}
    valid_users = []
    for user in users:
        u_vec = get_user_vector(user, use_cache=True)
        if u_vec is not None:
            user_vectors[user.id] = np.array(u_vec, dtype=np.float32)
            valid_users.append(user)
    
    if not valid_users:
        return results
    
    # Cargar servicios
    services = get_optimized_services_queryset(service_type, zone)
    if services is None:
        return results
    
    services_list = list(services[:top_k * 3])
    embeddings_map = get_service_embeddings_batch(services_list)
    
    # Convertir embeddings de servicios a numpy array
    service_embeddings = []
    valid_services = []
    for service in services_list:
        service_key = get_service_key(service)
        if service_key in embeddings_map:
            service_embeddings.append(np.array(embeddings_map[service_key], dtype=np.float32))
            valid_services.append(service)
    
    if not service_embeddings:
        return results
    
    service_embeddings_array = np.array(service_embeddings)
    
    # Normalizar embeddings de servicios para cálculo eficiente
    service_norms = np.linalg.norm(service_embeddings_array, axis=1, keepdims=True)
    service_norms[service_norms == 0] = 1  # Evitar división por cero
    service_embeddings_normalized = service_embeddings_array / service_norms
    
    # Calcular para cada usuario
    for user in valid_users:
        u_vec = user_vectors[user.id]
        u_vec_normalized = u_vec / np.linalg.norm(u_vec)
        
        # Calcular similitudes en lote (vectorizado)
        similarities = np.dot(service_embeddings_normalized, u_vec_normalized)
        
        # Obtener top_k servicios
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        recommendations = [
            (valid_services[i], float(similarities[i])) 
            for i in top_indices
        ]
        
        results[user.id] = recommendations
        
        # Cachear
        cache_key = get_recommendations_cache_key(
            user.id, service_type, zone.zone_id if zone else None, top_k
        )
        cache.set(cache_key, recommendations, timeout=300)
    
    return results