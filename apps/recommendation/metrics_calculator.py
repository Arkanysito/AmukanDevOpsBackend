import numpy as np
from django.core.cache import cache
from apps.recommendation.metrics import (
    calculate_precision_at_k, calculate_coverage, calculate_diversity,
    calculate_conversion_rate, RecommendationMetrics
)
from apps.recommendation.services import recommend_places
from apps.users.models import CustomUser
from apps.location.models import Zone
from apps.experiences.models import AccommodationService, ActivityService, Event
from apps.tracking.models import Interaction
from apps.core.constants import InteractionAction
from apps.travel.models import Itinerary, ItineraryItem

class RecommendationMetricsCalculator:
    """Calculadora de métricas para el sistema de recomendaciones"""
    
    def __init__(self):
        self.metrics_tracker = RecommendationMetrics()
    
    def calculate_all_metrics(self, test_users, service_type='accommodation', zone=None, k_values=[5, 10, 20]):
        """Calcula todas las métricas para un conjunto de usuarios de prueba"""
        print("🔍 Calculando métricas del sistema de recomendaciones...")
        print(f"📊 Usuarios de prueba: {len(test_users)}")
        print(f"🎯 Tipo de servicio: {service_type}")
        print(f"📍 Zona: {zone.name if zone else 'Todas'}")
        print()
        
        all_recommendations = []
        ground_truth = []
        
        for user in test_users:
            # Obtener recomendaciones
            recommendations = recommend_places(user, service_type, zone, top_k=max(k_values))
            recommended_ids = [self._get_service_id(service) for service, score in recommendations]
            all_recommendations.append(recommended_ids)
            
            # Obtener ground truth (interacciones reales del usuario)
            user_interactions = self._get_user_interactions(user, service_type)
            ground_truth.append(user_interactions)
            
            print(f"👤 Usuario {user.id}: {len(recommended_ids)} recomendaciones, {len(user_interactions)} interacciones")
        
        # Calcular métricas
        total_items = self._get_total_items(service_type, zone)
        metrics = self.metrics_tracker.evaluate_recommendations(all_recommendations, ground_truth, total_items)
        
        # Métricas adicionales
        metrics['diversity'] = self._calculate_overall_diversity(all_recommendations, service_type, zone)
        metrics['response_time'] = self._measure_average_response_time(test_users, service_type, zone)
        metrics['conversion_rate'] = self._calculate_overall_conversion_rate(all_recommendations, ground_truth)
        
        return metrics
    
    def _get_service_id(self, service):
        """Extrae el ID único del servicio"""
        if hasattr(service, 'service_id'):
            return service.service_id
        elif hasattr(service, 'event_id'):
            return service.event_id
        elif hasattr(service, 'place_id'):
            return service.place_id
        return getattr(service, 'id', None)
    
    def _get_user_interactions(self, user, service_type):
        """Obtiene las interacciones reales del usuario como ground truth - VERSIÓN CORREGIDA"""
        try:
            service_ids = []
            
            # Buscar interacciones de guardado de itinerarios
            save_interactions = Interaction.objects.filter(
                user_id=user,
                action=InteractionAction.SAVE_ITINERARY
            )
            
            print(f"🔍 Usuario {user.id}: {save_interactions.count()} itinerarios guardados")
            
            for interaction in save_interactions:
                # Obtener el itinerario desde el content_object
                if interaction.content_object and hasattr(interaction.content_object, 'itinerary_id'):
                    itinerary = interaction.content_object
                    print(f"  📋 Itinerario: {itinerary.name}")
                    
                    # Obtener todos los servicios de este itinerario
                    itinerary_services = self._get_services_from_itinerary(itinerary, service_type)
                    service_ids.extend(itinerary_services)
                    
                    print(f"  ➕ {len(itinerary_services)} servicios del tipo {service_type}")
            
            # También buscar en metadata por si el itinerario está ahí
            for interaction in save_interactions:
                if interaction.metadata and 'itinerary_info' in interaction.metadata:
                    itinerary_info = interaction.metadata['itinerary_info']
                    if 'itinerary_id' in itinerary_info:
                        try:
                            itinerary = Itinerary.objects.get(itinerary_id=itinerary_info['itinerary_id'])
                            itinerary_services = self._get_services_from_itinerary(itinerary, service_type)
                            service_ids.extend(itinerary_services)
                            print(f"  📦 {len(itinerary_services)} servicios adicionales desde metadata")
                        except Itinerary.DoesNotExist:
                            pass
            
            unique_ids = list(set(service_ids))  # Remover duplicados
            print(f"✅ Total servicios únicos: {len(unique_ids)}")
            return unique_ids
            
        except Exception as e:
            print(f"⚠️ Error obteniendo interacciones para usuario {user.id}: {e}")
            return []

    def _get_services_from_itinerary(self, itinerary, target_service_type):
        """Extrae los IDs de servicio de un itinerario filtrados por tipo"""
        service_ids = []
        try:
            # Obtener todos los items del itinerario
            items = ItineraryItem.objects.filter(itinerary_id=itinerary)
            
            print(f"    📝 Itinerario tiene {items.count()} items")
            
            for item in items:
                if item.reservable:
                    # Determinar el tipo de servicio basado en el content_type
                    content_type = item.content_type
                    service_obj = item.reservable
                    
                    # Mapear content_type a nuestro service_type
                    actual_service_type = self._map_content_type_to_service_type(content_type)
                    
                    # Solo incluir si coincide con el tipo objetivo
                    if actual_service_type == target_service_type:
                        service_id = self._get_service_id(service_obj)
                        if service_id:
                            service_ids.append(service_id)
                            print(f"      ✅ {content_type.model}: {service_id}")
            
            return service_ids
            
        except Exception as e:
            print(f"⚠️ Error extrayendo servicios del itinerario {itinerary.itinerary_id}: {e}")
            return []

    def _map_content_type_to_service_type(self, content_type):
        """Mapea content_type de Django a nuestros service_types"""
        model_name = content_type.model.lower()
        
        # Mapeo de modelos a tipos de servicio
        type_mapping = {
            'accommodationservice': 'accommodation',
            'activityservice': 'activity', 
            'eventservice': 'event',
            'event': 'event',
            'place': 'restaurant',
            'transportservice': 'transport'
        }
        
        return type_mapping.get(model_name, 'unknown')

    def _get_total_items(self, service_type, zone):
        """Obtiene el total de items en el catálogo"""
        try:
            if service_type == 'accommodation':
                queryset = AccommodationService.objects.all()
            elif service_type == 'activity':
                queryset = ActivityService.objects.all()
            elif service_type == 'event':
                queryset = Event.objects.all()
            else:
                queryset = AccommodationService.objects.all()  # Default
            
            if zone:
                queryset = queryset.filter(place_id__zone_id=zone)
                
            return queryset.count()
        except:
            return 1000  # Fallback
    
    def _calculate_overall_diversity(self, all_recommendations, service_type, zone):
        """Calcula diversidad general de todas las recomendaciones"""
        try:
            # Obtener servicios únicos recomendados
            all_service_ids = set()
            for recs in all_recommendations:
                all_service_ids.update(recs)
            
            # Obtener embeddings de estos servicios
            services_with_embeddings = []
            for service_id in list(all_service_ids)[:50]:  # Limitar para performance
                service = self._get_service_by_id(service_id, service_type)
                if service and hasattr(service, 'embedding') and service.embedding:
                    services_with_embeddings.append(service)
            
            if len(services_with_embeddings) > 1:
                return calculate_diversity(services_with_embeddings)
            return 0.0
            
        except Exception as e:
            print(f"⚠️ Error calculando diversidad: {e}")
            return 0.0
    
    def _get_service_by_id(self, service_id, service_type):
        """Obtiene un servicio por ID"""
        try:
            if service_type == 'accommodation':
                return AccommodationService.objects.get(service_id=service_id)
            elif service_type == 'activity':
                return ActivityService.objects.get(service_id=service_id)
            elif service_type == 'event':
                return Event.objects.get(event_id=service_id)
        except:
            return None
    
    def _measure_average_response_time(self, test_users, service_type, zone, samples=5):
        """Mide el tiempo de respuesta promedio"""
        import time
        
        times = []
        for user in test_users[:samples]:  # Limitar muestras
            start_time = time.time()
            recommend_places(user, service_type, zone, top_k=10, use_cache=True)
            end_time = time.time()
            times.append(end_time - start_time)
        
        return np.mean(times) if times else 0.0
    
    def _calculate_overall_conversion_rate(self, all_recommendations, ground_truth):
        """Calcula tasa de conversión general"""
        total_recommended = 0
        total_converted = 0
        
        for recs, truth in zip(all_recommendations, ground_truth):
            if recs:  # Solo si hay recomendaciones
                total_recommended += len(recs)
                total_converted += len(set(recs) & set(truth))
        
        return total_converted / total_recommended if total_recommended > 0 else 0.0
    
    def print_metrics_report(self, metrics):
        """Imprime un reporte bonito de las métricas"""
        print("\n" + "="*60)
        print("📈 REPORTE DE MÉTRICAS - SISTEMA DE RECOMENDACIONES")
        print("="*60)
        
        # Precision y Recall
        for k in [5, 10, 20]:
            precision_key = f'precision@{k}'
            recall_key = f'recall@{k}'
            if precision_key in metrics:
                print(f"🎯 Precision@{k}: {metrics[precision_key]:.3f}")
            if recall_key in metrics:
                print(f"🔍 Recall@{k}:    {metrics[recall_key]:.3f}")
        
        # Otras métricas
        print(f"📊 Cobertura:        {metrics.get('coverage', 0):.3f}")
        print(f"🌈 Diversidad:       {metrics.get('diversity', 0):.3f}")
        print(f"⚡ Tiempo respuesta: {metrics.get('response_time', 0):.3f}s")
        print(f"💸 Tasa conversión:  {metrics.get('conversion_rate', 0):.3f}")
        
        print("="*60)
        
        # Interpretación
        self._print_interpretation(metrics)
    
    def _print_interpretation(self, metrics):
        """Proporciona interpretación de las métricas"""
        print("\n💡 INTERPRETACIÓN:")
        
        precision = metrics.get('precision@10', 0)
        if precision > 0.3:
            print("✅ Excelente precisión - Las recomendaciones son muy relevantes")
        elif precision > 0.15:
            print("⚠️  Precisión aceptable - Hay espacio para mejora")
        else:
            print("❌ Precisión baja - Revisar el algoritmo de recomendación")
        
        diversity = metrics.get('diversity', 0)
        if diversity > 0.7:
            print("✅ Alta diversidad - Buen balance entre variedad y relevancia")
        elif diversity > 0.4:
            print("⚠️  Diversidad moderada - Considerar aumentar variedad")
        else:
            print("❌ Baja diversidad - Riesgo de sobre-especialización")
        
        response_time = metrics.get('response_time', 0)
        if response_time < 0.5:
            print("✅ Excelente rendimiento - Respuesta muy rápida")
        elif response_time < 2.0:
            print("⚠️  Rendimiento aceptable - Considerar optimizaciones")
        else:
            print("❌ Rendimiento lento - Revisar optimización del sistema")