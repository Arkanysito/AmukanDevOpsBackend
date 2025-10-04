# ============================================================================
# Comando para limpiar cache de recomendaciones
# ============================================================================

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Limpia el cache del sistema de recomendaciones'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='ID de usuario específico para limpiar cache'
        )
    
    def handle(self, *args, **options):
        from apps.recommendation.services import (
            RecommendationCacheMonitor,
            invalidate_user_vector_cache
        )
        from django.core.cache import cache
        
        user_id = options.get('user_id')
        
        if user_id:
            self.stdout.write(f"Limpiando cache para usuario {user_id}...")
            invalidate_user_vector_cache(user_id)
            
            # Limpiar recomendaciones específicas del usuario
            service_types = ['activity', 'accommodation', 'restaurant', 'event', 'place']
            for service_type in service_types:
                # Limpiar para diferentes zonas (aproximación)
                for i in range(100):  # Máximo 100 zonas
                    cache_key = f"recommendations_{user_id}_{service_type}_*_{i}_*"
                    try:
                        cache.delete(cache_key)
                    except:
                        pass
            
            self.stdout.write(
                self.style.SUCCESS(f"✓ Cache limpiado para usuario {user_id}")
            )
        else:
            self.stdout.write("Limpiando todo el cache de recomendaciones...")
            result = RecommendationCacheMonitor.clear_all_recommendation_caches()
            self.stdout.write(self.style.SUCCESS(f"✓ {result}"))
