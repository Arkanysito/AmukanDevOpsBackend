import logging
from celery import shared_task
from apps.users.models import CustomUser
from apps.users.services import UserProfileAnalyzer
from apps.recommendation.services import invalidate_user_vector_cache

logger = logging.getLogger(__name__)

@shared_task
def run_profile_analysis_task(user_id):
    """
    Ejecuta el análisis de perfil de usuario y luego invalida su caché de vector.
    """
    try:
        user = CustomUser.objects.get(id=user_id)
        
        # 1. Ejecuta el analizador para aprender de las interacciones
        analyzer = UserProfileAnalyzer(user)
        analyzer.analyze_recent_interactions(days=30) # O el rango que prefieras
        
        # 2. Invalida el caché para forzar el recálculo la próxima vez
        invalidate_user_vector_cache(user_id)
        
        logger.info(f"Análisis de perfil y limpieza de caché completados para {user.email}")
        
    except CustomUser.DoesNotExist:
        logger.warning(f"Usuario {user_id} no encontrado para análisis de perfil.")
    except Exception as e:
        logger.error(f"Error en run_profile_analysis_task para {user_id}: {e}", exc_info=True)

@shared_task
def clear_user_vector_cache_task(user_id):
    """
    Una tarea más simple que solo invalida el caché.
    """
    try:
        invalidate_user_vector_cache(user_id)
        logger.info(f"Caché de vector invalidado para usuario {user_id}")
    except Exception as e:
        logger.error(f"Error en clear_user_vector_cache_task para {user_id}: {e}", exc_info=True)