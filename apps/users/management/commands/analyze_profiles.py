import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.users.models import CustomUser
from apps.tracking.models import Interaction
from apps.users.services import UserProfileAnalyzer
from apps.recommendation.services import invalidate_user_vector_cache # ¡Importante!

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Analiza interacciones recientes y favoritos actuales para actualizar perfiles de interés.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Iniciando análisis de perfiles de usuario..."))
        
        # 1. Encontrar usuarios que tuvieron actividad reciente (últimas 24 horas)
        # Esto es mucho más eficiente que iterar sobre TODOS los usuarios.
        cutoff_date = timezone.now() - timedelta(days=1)
        recent_user_ids = Interaction.objects.filter(
            interaction_date__gte=cutoff_date
        ).values_list('user_id', flat=True).distinct()
        
        users_to_update = CustomUser.objects.filter(id__in=recent_user_ids, is_active=True)
        
        if not users_to_update.exists():
            self.stdout.write(self.style.SUCCESS("No hay usuarios con actividad reciente. Saliendo."))
            return

        self.stdout.write(f"Se analizarán {users_to_update.count()} usuarios activos...")
        
        count = 0
        failed_count = 0
        
        # 2. Analizar a cada usuario
        for user in users_to_update:
            try:
                analyzer = UserProfileAnalyzer(user)
                # Llama a la función que analiza interacciones Y favoritos
                analyzer.analyze_recent_interactions(days=30) 
                
                # 3. ¡CRÍTICO! Invalidar el caché del vector de este usuario
                # Esto fuerza a que se recalcule con los nuevos intereses
                invalidate_user_vector_cache(user.id)
                
                count += 1
            except Exception as e:
                logger.error(f"Error analizando perfil para {user.email}: {e}", exc_info=True)
                failed_count += 1
        
        self.stdout.write(self.style.SUCCESS(f"Análisis completado. {count} perfiles actualizados."))
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f"{failed_count} perfiles fallaron al actualizar."))