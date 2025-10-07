# ============================================================================
# Comando para precalentar cache manualmente
# ============================================================================

from django.core.management.base import BaseCommand
from apps.recommendation.services import warmup_recommendation_system
from apps.users.models import CustomUser
from apps.location.models import Zone


class Command(BaseCommand):
    help = 'Precalienta el cache del sistema de recomendaciones'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=10,
            help='Número de usuarios para precalentar (default: 10)'
        )
        
        parser.add_argument(
            '--clear-first',
            action='store_true',
            help='Limpiar cache antes de precalentar'
        )
    
    def handle(self, *args, **options):
        from apps.recommendation.services import (
            recommend_places_batch,
            RecommendationCacheMonitor,
            get_user_vector
        )
        
        self.stdout.write("Iniciando warmup del sistema de recomendaciones...")
        
        # Limpiar cache si se solicita
        if options['clear_first']:
            self.stdout.write("Limpiando cache existente...")
            result = RecommendationCacheMonitor.clear_all_recommendation_caches()
            self.stdout.write(self.style.SUCCESS(f"Cache limpiado: {result}"))
        
        # Warmup del modelo
        warmup_recommendation_system()
        self.stdout.write(self.style.SUCCESS("✓ Modelo de embeddings cargado"))
        
        # Obtener usuarios activos
        users = CustomUser.objects.filter(is_active=True)[:options['users']]
        
        if not users:
            self.stdout.write(self.style.WARNING("No se encontraron usuarios activos"))
            return
        
        self.stdout.write(f"Precalentando vectores para {len(users)} usuarios...")
        
        # Precalcular vectores de usuarios
        for user in users:
            get_user_vector(user, use_cache=True)
        
        self.stdout.write(self.style.SUCCESS(f"✓ Vectores de usuario cacheados: {len(users)}"))
        
        # Precalentar recomendaciones para servicios comunes
        service_types = ['activity', 'accommodation', 'restaurant', 'event']
        
        # Obtener específicamente Viña del Mar
        try:
            vina_del_mar = Zone.objects.get(name__icontains='Viña del Mar')
            target_zones = [vina_del_mar]
            self.stdout.write(f"✓ Enfocándose en: {vina_del_mar.name}")
        except Zone.DoesNotExist:
            # Si no existe Viña del Mar, usar las primeras zonas como fallback
            self.stdout.write(self.style.WARNING("Viña del Mar no encontrada, usando zonas disponibles"))
            target_zones = Zone.objects.all()[:3]
        
        total_cached = 0
        
        for service_type in service_types:
            self.stdout.write(f"Precalentando {service_type}...")
            
            for zone in target_zones:
                results = recommend_places_batch(
                    list(users), 
                    service_type, 
                    zone, 
                    top_k=20
                )
                total_cached += len(results)
                
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {service_type} en {zone.name}: {len(results)} usuarios")
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Warmup completado: {total_cached} recomendaciones cacheadas para Viña del Mar"
            )
        )
        
        # Mostrar stats del cache
        stats = RecommendationCacheMonitor.get_cache_stats()
        self.stdout.write(f"\nEstadísticas del cache:\n{stats}")