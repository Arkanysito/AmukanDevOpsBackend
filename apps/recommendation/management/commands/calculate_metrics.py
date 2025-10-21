import logging
import time
import numpy as np
from django.core.cache import cache
from django.core.management.base import BaseCommand

from apps.recommendation.metrics import RecommendationMetrics, calculate_diversity
from apps.recommendation.services import (
    recommend_places, get_user_vector, get_optimized_services_queryset, 
    cosine_similarity_numpy
)
from apps.users.models import CustomUser
from apps.location.models import Zone, Place
from apps.experiences.models import AccommodationService, ActivityService, Event

logger = logging.getLogger(__name__)

class RecommendationMetricsCalculator:
    """
    Calculadora de métricas para el sistema de recomendaciones.
    Evalúa la consistencia del ranking basado en la similitud con el perfil.
    """
    
    def __init__(self):
        self.metrics_tracker = RecommendationMetrics()

    def calculate_all_metrics(self, test_users, service_type='accommodation', zone=None, k_values=[5, 10, 20]):
        """Calcula métricas offline para un conjunto de usuarios de prueba."""
        print("🔍 Calculando métricas del sistema de recomendaciones (Evaluación Offline)...")
        print(f"📊 Usuarios de prueba: {len(test_users)}")
        print(f"🎯 Tipo de servicio: {service_type}")
        print(f"📍 Zona: {zone.name if zone else 'Todas'}")
        print(f"🔢 K para Prec/Rec: {k_values}")
        print("\n--- Definiendo Relevancia: Items con mayor similitud al vector de perfil del usuario ---")

        # --- Variables para recolectar datos ---
        all_recommendations_ids = []    # Lista de listas de IDs para Prec/Rec/MAP/Coverage
        all_recommended_objects = []  # Lista de listas de OBJETOS para Diversidad
        profile_relevant_items = []   # Lista de listas de IDs relevantes según perfil

        max_k = max(k_values) if k_values else 20

        # --- Bucle principal por usuario ---
        for user in test_users:
            print(f"\n👤 Procesando Usuario {user.id} ({user.email})...")

            # 1. Obtener recomendaciones reales (lista de tuplas (servicio, score))
            recommendations_tuples = recommend_places(user, service_type, zone, top_k=max_k, use_cache=False) # Forzar recálculo

            # Preparar listas para este usuario
            recommended_ids_for_user = []
            recommended_objects_for_user = []
            for service, score in recommendations_tuples:
                if service:
                    service_id = self._get_service_id(service)
                    if service_id:
                        recommended_ids_for_user.append(service_id)
                        recommended_objects_for_user.append(service) # Guardar el objeto

            # Agregar a las listas generales
            all_recommendations_ids.append(recommended_ids_for_user)
            all_recommended_objects.append(recommended_objects_for_user)
            print(f"  📋 Recomendó ({len(recommended_ids_for_user)}): {recommended_ids_for_user[:5]}...")

            # 2. Obtener los items "idealmente" relevantes según el perfil (lista de IDs)
            relevant_ids = self._get_profile_relevant_items(user, service_type, zone)
            profile_relevant_items.append(relevant_ids)
            print(f"  ✨ Perfil sugiere ({len(relevant_ids)}): {relevant_ids[:5]}...")

            # 3. Debug de coincidencia (opcional)
            matches = set(recommended_ids_for_user) & set(relevant_ids)
            print(f"  🔗 Coincidencias Top-{max_k}: {len(matches)}")
            if matches:
                 print(f"     ✅ IDs: {list(matches)[:3]}...")

        # --- Calcular Métricas ---
        total_items = self._get_total_items(service_type, zone)
        print(f"\n📊 Total items en catálogo ({service_type}, Zona: {'Todas' if not zone else zone.name}): {total_items}")

        if not all_recommendations_ids: # Verificar si se generaron recomendaciones
            print("⚠️ No se generaron recomendaciones. No se pueden calcular métricas.")
            return {}

        # 4. Calcular métricas basadas en IDs (Prec/Rec/MAP/Coverage)
        metrics = self.metrics_tracker.evaluate_recommendations(
            all_recommendations_ids,    # Pasa IDs
            profile_relevant_items,     # Pasa IDs relevantes
            total_items
        )

        # 5. Calcular métricas adicionales que necesitan objetos o medir tiempo
        metrics['diversity'] = self._calculate_overall_diversity(
            all_recommended_objects,    # <-- ¡CORREGIDO! Pasa la lista de OBJETOS
            service_type
        )
        metrics['response_time'] = self._measure_average_response_time(test_users, service_type, zone, max_k)

        return metrics

    def _get_profile_relevant_items(self, user, service_type, zone, similarity_threshold=0.6, top_n_ratio=0.1, min_relevant=5, max_relevant=15):
        """
        Obtiene los items considerados "relevantes" para el perfil del usuario.
        Relevancia definida como alta similitud de embedding con el vector del usuario.
        """
        try:
            user_vector = get_user_vector(user, use_cache=False) # Forzar recálculo para consistencia
            if user_vector is None:
                print(f"  ⚠️ Usuario {user.id}: No se pudo generar vector. No se puede definir relevancia.")
                return []

            services_qs = get_optimized_services_queryset(service_type, zone)
            if services_qs is None or not services_qs.exists():
                print(f"  ⚠️ Usuario {user.id}: No hay servicios disponibles en catálogo.")
                return []

            # Calcular similitud para TODOS los servicios (o una muestra grande)
            # Limitar a 200 para no tardar demasiado en la evaluación
            services_list = list(services_qs.exclude(embedding=None)[:200]) 
            similarities = []
            
            for service in services_list:
                try:
                    service_embedding = np.array(service.embedding, dtype=np.float32)
                    if service_embedding.size == 0: continue # Skip empty embeddings
                    
                    similarity = cosine_similarity_numpy(user_vector, service_embedding)
                    service_id = self._get_service_id(service)
                    if service_id:
                        similarities.append((service_id, similarity, getattr(service, 'name', 'N/A')))
                        
                except (ValueError, TypeError) as emb_err:
                    # logger.warning(f"Skipping service {self._get_service_id(service)} due to embedding error: {emb_err}")
                    continue # Ignorar servicios con embeddings inválidos

            if not similarities:
                print(f"  ⚠️ Usuario {user.id}: No se pudieron calcular similitudes para definir relevancia.")
                return []

            # Ordenar por similitud descendente
            similarities.sort(key=lambda x: x[1], reverse=True)

            # Definir items relevantes como el top N% o aquellos sobre un umbral
            num_relevant_target = max(min_relevant, min(max_relevant, int(len(similarities) * top_n_ratio)))
            relevant_items = [sid for sid, sim, name in similarities[:num_relevant_target]]

            # Opcional: Filtrar por umbral mínimo de similitud
            # relevant_items = [sid for sid, sim, name in similarities if sim >= similarity_threshold]

            if relevant_items:
                 min_sim_in_relevant = similarities[len(relevant_items)-1][1]
                 print(f"  ✨ Perfil sugiere {len(relevant_items)} items (Top {num_relevant_target} o {top_n_ratio*100:.0f}%, similitud >= {min_sim_in_relevant:.3f})")
                 # Mostrar los 3 más relevantes para el perfil
                 #for i, (sid, sim, name) in enumerate(similarities[:3]):
                 #     print(f"     ➡️ {i+1}. {name} (Sim: {sim:.3f})")
            else:
                 print(f"  ⚠️ Usuario {user.id}: Ningún item superó los criterios de relevancia del perfil.")

            return relevant_items

        except Exception as e:
            logger.error(f"⚠️ Error obteniendo items relevantes para perfil {user.id}: {e}", exc_info=True)
            return []

    # --- Métodos Helper ---

    def _get_service_id(self, service):
        """Extrae el ID único del servicio"""
        if service is None: return None
        if hasattr(service, 'service_id') and service.service_id: return str(service.service_id)
        if hasattr(service, 'event_id') and service.event_id: return str(service.event_id)
        if hasattr(service, 'place_id') and service.place_id: return str(service.place_id)
        return str(getattr(service, 'id', None)) # Asegurar que sea string

    def _get_total_items(self, service_type, zone):
        """Obtiene el total de items en el catálogo"""
        try:
            # Usar el mismo queryset que usa el recomendador para consistencia
            queryset = get_optimized_services_queryset(service_type, zone)
            if queryset is not None:
                return queryset.count()
            else: # Fallback si get_optimized_services_queryset falla para un tipo
                 logger.warning(f"No se pudo obtener queryset optimizado para {service_type}, usando conteo general.")
                 if service_type == 'activity': base_qs = ActivityService.objects.all()
                 elif service_type == 'event': base_qs = Event.objects.all()
                 else: base_qs = Place.objects.all() # Asume Place para accommodation, restaurant, place

                 # Aplicar filtro de zona si aplica (simplificado)
                 if zone:
                     if hasattr(base_qs.model, 'zone_id'):
                         base_qs = base_qs.filter(zone_id=zone)
                     elif hasattr(base_qs.model, 'place_id__zone_id'):
                          base_qs = base_qs.filter(place_id__zone_id=zone)
                 return base_qs.count()
        except Exception as e:
            logger.error(f"Error contando total_items: {e}")
            return 1000 # Fallback muy genérico

    def _calculate_overall_diversity(self, all_recommended_objects: list[list[any]], service_type: str) -> float:
        """
        Calcula la diversidad general promedio de las listas de recomendaciones.
        Mide la dissimilaridad intra-lista promedio usando embeddings.
        """
        print("\n🌈 Calculando Diversidad Intra-Lista Promedio...")
        if not all_recommended_objects:
            print("   ⚠️ No hay recomendaciones para calcular diversidad.")
            return 0.0

        user_diversities = []
        skipped_users = 0

        for user_recs in all_recommended_objects:
            # Filtrar solo objetos con embeddings válidos de esta lista
            services_with_embeddings = []
            for service in user_recs:
                 if service and hasattr(service, 'embedding') and service.embedding is not None:
                     # Verificar si el embedding no está vacío (lista o ndarray)
                     if isinstance(service.embedding, (list, np.ndarray)) and len(service.embedding) > 0:
                          services_with_embeddings.append(service)

            if len(services_with_embeddings) > 1:
                try:
                    # Llama a la función importada de metrics.py
                    diversity_score = calculate_diversity(services_with_embeddings)
                    user_diversities.append(diversity_score)
                except Exception as e:
                    logger.warning(f"Error calculando diversidad para una lista: {e}")
                    skipped_users += 1
            elif len(services_with_embeddings) <= 1:
                # Si hay 0 o 1 item con embedding, la diversidad es 0
                 user_diversities.append(0.0)

        if not user_diversities:
             print("   ⚠️ No se pudo calcular la diversidad para ninguna lista (quizás faltan embeddings).")
             return 0.0

        average_diversity = np.mean(user_diversities)
        print(f"   🌈 Diversidad promedio: {average_diversity:.3f} (calculada sobre {len(user_diversities)} listas)")
        if skipped_users > 0:
             print(f"   ⚠️ Se omitieron {skipped_users} listas por errores.")
             
        return average_diversity 
    
    def _measure_average_response_time(self, test_users, service_type, zone, k, samples=5):
        """Mide el tiempo de respuesta promedio"""
        times = []
        # Usar un subconjunto de usuarios para no tardar demasiado
        sample_users = test_users[:min(len(test_users), samples)]
        if not sample_users: return 0.0

        print(f"\n⏱️  Midiendo tiempo de respuesta (promedio sobre {len(sample_users)} usuarios)...")
        for user in sample_users:
            start_time = time.time()
            # Llamar a recommend_places con caché para simular uso real
            recommend_places(user, service_type, zone, top_k=k, use_cache=True)
            end_time = time.time()
            times.append(end_time - start_time)
            # Invalidar caché específico para la siguiente medición si se desea más precisión
            # cache_key = get_recommendations_cache_key(...)
            # cache.delete(cache_key)

        avg_time = np.mean(times)
        print(f"  ⏱️  Tiempo promedio: {avg_time:.4f} segundos")
        return avg_time

    # Eliminada la función _calculate_overall_conversion_rate basada en ground truth simulado.

    def print_metrics_report(self, metrics):
        """Imprime un reporte bonito de las métricas"""
        if not metrics:
            print("\n" + "="*60)
            print("⚠️ REPORTE DE MÉTRICAS - No se calcularon métricas.")
            print("="*60)
            return
            
        print("\n" + "="*60)
        print("📈 REPORTE DE MÉTRICAS - SISTEMA DE RECOMENDACIONES")
        print("(Relevancia definida por similitud al perfil de usuario)")
        print("="*60)

        # MAP
        print(f"⭐ MAP (Mean Average Precision): {metrics.get('map', 0):.3f}")

        # Precision y Recall
        for k_str in metrics:
            if k_str.startswith('precision@'):
                k = k_str.split('@')[1]
                recall_key = f'recall@{k}'
                print(f"🎯 Precision@{k}: {metrics[k_str]:.3f}")
                if recall_key in metrics:
                    print(f"🔍 Recall@{k}:    {metrics[recall_key]:.3f}")

        # Otras métricas
        print("-" * 20)
        print(f"📊 Cobertura:    {metrics.get('coverage', 0):.3f}")
        print(f"🌈 Diversidad:   {metrics.get('diversity', 0):.3f}")
        print(f"⚡ Tiempo Resp.: {metrics.get('response_time', 0):.4f}s")
        # print(f"💸 Tasa Conversión (Simulada): {metrics.get('conversion_rate', 0):.3f}") # Eliminada

        print("="*60)
        self._print_interpretation(metrics)

    def _print_interpretation(self, metrics):
        """Proporciona interpretación de las métricas"""
        print("\n💡 INTERPRETACIÓN (basada en consistencia con perfil):")

        map_score = metrics.get('map', 0)
        if map_score > 0.4:
            print("✅ Buen MAP - El ranking refleja bien la similitud con el perfil.")
        elif map_score > 0.2:
            print("⚠️ MAP aceptable - El orden podría mejorar.")
        else:
            print("❌ MAP bajo - El ranking es inconsistente con la similitud del perfil.")

        precision10 = metrics.get('precision@10', 0)
        if precision10 > 0.3:
            print("✅ Buena Precisión@10 - Los Top 10 suelen ser muy similares al perfil.")
        elif precision10 > 0.1:
            print("⚠️ Precisión@10 aceptable.")
        else:
            print("❌ Baja Precisión@10 - Pocos items del Top 10 son muy similares al perfil.")

        # Interpretación de Cobertura, Diversidad, Tiempo (sin cambios)
        coverage = metrics.get('coverage', 0)
        if coverage > 0.3:
            print("✅ Buena Cobertura - El sistema recomienda una parte significativa del catálogo.")
        elif coverage > 0.1:
             print("⚠️ Cobertura moderada - Muchos items nunca son recomendados.")
        else:
             print("❌ Baja Cobertura - El sistema recomienda muy pocos items diferentes.")
             
        # ... (Interpretación de Diversidad y Tiempo Respuesta igual que antes) ...
        response_time = metrics.get('response_time', 0)
        if response_time < 0.5:
             print("✅ Excelente rendimiento - Respuesta muy rápida.")
        elif response_time < 2.0:
             print("⚠️ Rendimiento aceptable - Considerar optimizaciones si empeora.")
        else:
             print("❌ Rendimiento lento - Revisar caché y optimización de queries.")


# ============================================================================
# Comando de Django
# ============================================================================
class Command(BaseCommand):
    """Comando de Django para calcular métricas de recomendaciones offline"""

    help = 'Calcula métricas de evaluación offline para el sistema de recomendaciones'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zone', type=str, help='(Opcional) ID (UUID) de la zona para filtrar.'
        )
        parser.add_argument(
            '--service-type', type=str, default='activity', # Cambiado default a 'activity'
            choices=['accommodation', 'activity', 'event', 'restaurant', 'place'],
            help='Tipo de servicio a evaluar (default: activity)'
        )
        parser.add_argument(
            '--users', type=int, default=10,
            help='Número de usuarios (aleatorios) a evaluar (default: 10)'
        )
        parser.add_argument(
            '--k-values', type=str, default='5,10,20',
            help='Valores de k para Prec/Rec (separados por coma, default: 5,10,20)'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🚀 Iniciando cálculo de métricas de recomendaciones..."))

        zone_id = options.get('zone')
        service_type = options.get('service_type')
        num_users = options.get('users')
        k_values_str = options.get('k_values')

        try:
            k_values = [int(k.strip()) for k in k_values_str.split(',')]
            if not k_values: raise ValueError("k_values no puede estar vacío.")
        except ValueError:
            self.stderr.write(self.style.ERROR("❌ Formato inválido para --k-values. Use comas, ej: 5,10,20"))
            return

        zone = None
        if zone_id:
            try:
                zone = Zone.objects.get(zone_id=zone_id)
                self.stdout.write(f"📍 Zona seleccionada: {zone.name}")
            except Zone.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"❌ Zona con ID {zone_id} no encontrada."))
                return
            except ValueError:
                 self.stderr.write(self.style.ERROR(f"❌ ID de Zona inválido: {zone_id} (debe ser UUID)."))
                 return

        # Seleccionar usuarios aleatorios en lugar de los primeros N
        all_user_ids = CustomUser.objects.filter(is_active=True).values_list('id', flat=True)
        if len(all_user_ids) < num_users:
             self.stdout.write(self.style.WARNING(f"⚠️  Solo hay {len(all_user_ids)} usuarios activos, se usarán todos."))
             test_user_ids = all_user_ids
        else:
             test_user_ids = np.random.choice(all_user_ids, size=num_users, replace=False)
             
        test_users = CustomUser.objects.filter(id__in=list(test_user_ids)).exclude(email='admin@admin.cl')
        self.stdout.write(f"🔍 Evaluando {len(test_users)} usuarios aleatorios...")

        if not test_users.exists():
            self.stderr.write(self.style.ERROR("❌ No se encontraron usuarios activos para evaluar."))
            return

        # Calcular métricas
        try:
            calculator = RecommendationMetricsCalculator()
            metrics = calculator.calculate_all_metrics(
                test_users=list(test_users), # Pasar como lista
                service_type=service_type,
                zone=zone,
                k_values=k_values
            )
        except Exception as e:
             self.stderr.write(self.style.ERROR(f"❌ Error durante el cálculo de métricas: {e}"))
             logger.exception("Error en handle de evaluate_recs") # Log completo
             return

        # Imprimir reporte
        calculator.print_metrics_report(metrics)

        self.stdout.write(self.style.SUCCESS("✅ Cálculo de métricas finalizado."))