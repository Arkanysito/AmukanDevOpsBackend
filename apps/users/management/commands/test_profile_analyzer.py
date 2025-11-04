import logging
import math
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache

# Importa todos los modelos y servicios necesarios
from apps.users.models import CustomUser, UserInterest, UserFavorite, Interest
from apps.location.models import Place
from apps.tracking.models import Interaction
from apps.core.constants import InteractionAction
from apps.recommendation.services import get_user_vector_cache_key

# --- CONFIGURACIÓN DE LA PRUEBA ---
# ▼▼▼ ¡AJUSTA ESTOS VALORES! ▼▼▼
TEST_USER_EMAIL = "ethan@usm.cl"
# Busca un ID de un 'Place' que sea un restaurante en tu BD
TEST_PLACE_ID = "f674230b-d3f9-4384-bf90-4083edaf0348" 
# --------------------------------

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Ejecuta una prueba de "Antes y Después" del UserProfileAnalyzer.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Email del usuario para probar (opcional)',
            default=TEST_USER_EMAIL
        )
        parser.add_argument(
            '--place_id',
            type=str,
            help='ID del Place (restaurante) para usar como favorito (opcional)',
            default=TEST_PLACE_ID
        )

    def handle(self, *args, **options):
        user_email = options['email']
        place_id = options['place_id']
        
        self.stdout.write(self.style.NOTICE(f"--- Iniciando Prueba de Análisis de Perfil para: {user_email} ---"))

        # --- OBTENER OBJETOS DE PRUEBA ---
        try:
            user = CustomUser.objects.get(email=user_email)
            place = Place.objects.get(place_id=place_id)
            place_type = ContentType.objects.get_for_model(place)
        except CustomUser.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Error: Usuario {user_email} no encontrado."))
            return
        except Place.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Error: Place {place_id} no encontrado."))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error de configuración: {e}"))
            return

        # =================================================================
        # PASO 1: SETUP (Estado "Antes")
        # =================================================================
        self.stdout.write(self.style.NOTICE("PASO 1: Limpiando estado 'Antes'..."))
        UserInterest.objects.filter(user_id=user).delete()
        UserFavorite.objects.filter(user_id=user).delete()
        Interaction.objects.filter(user_id=user).delete()
        
        # Limpiar el caché por si acaso
        cache_key = get_user_vector_cache_key(user.id)
        cache.delete(cache_key)

        self.stdout.write("Intereses, Favoritos, Interacciones y Caché previos... ELIMINADOS.")

        # =================================================================
        # PASO 2: SIMULAR EVIDENCIA
        # =================================================================
        self.stdout.write(self.style.NOTICE("PASO 2: Creando 'Evidencia' (Interacciones y Favoritos)..."))
        
        # Evidencia A: Un Favorito (Restaurante)
        UserFavorite.objects.create(
            user_id=user,
            content_type=place_type,
            object_id=place.place_id
        )
        self.stdout.write(f"  > Evidencia A (Favorito) creada: {place.name}")

        # Evidencia B: Una Interacción de Guardar Itinerario (reciente)
        interaction_time = timezone.now() - timedelta(hours=1)
        Interaction.objects.create(
            user_id=user,
            action=InteractionAction.SAVE_ITINERARY,
            interaction_date=interaction_time,
            metadata={
                "user_preferences": {"gastronomy": True},
                "service_distribution": {"comida": {"count": 3}}
            }
        )
        self.stdout.write("  > Evidencia B (Interacción SAVE_ITINERARY) creada.")

        # =================================================================
        # PASO 3: EJECUTAR EL ANALIZADOR
        # =================================================================
        self.stdout.write(self.style.NOTICE("PASO 3: Ejecutando 'manage.py analyze_profiles'..."))
        
        try:
            # Llama al otro comando de gestión
            call_command('analyze_profiles')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"El comando 'analyze_profiles' falló: {e}"))
            return

        # =================================================================
        # PASO 4: VERIFICAR RESULTADOS (Estado "Después")
        # =================================================================
        self.stdout.write(self.style.NOTICE("PASO 4: Verificando estado 'Después'..."))
        
        # El analizador debió crear un interés "Gastronomía"
        try:
            gastronomia_interest = UserInterest.objects.get(
                user_id=user,
                interest_id__name="Gastronomía"
            )
            
            # Cálculo del peso esperado:
            # 0.2 (favorito) + 0.3 (pref. itinerario) + 0.2 (serv. itinerario) = 0.7
            expected_weight = 0.7
            
            if math.isclose(gastronomia_interest.weight, expected_weight, rel_tol=1e-9):
                self.stdout.write(self.style.SUCCESS(
                    f"  [ÉXITO] Interés 'Gastronomía' creado con peso correcto ({gastronomia_interest.weight})"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"  [FALLO] Peso incorrecto para 'Gastronomía'. Esperado: {expected_weight}, Obtenido: {gastronomia_interest.weight}"
                ))

        except UserInterest.DoesNotExist:
            self.stdout.write(self.style.ERROR("  [FALLO] El analizador NO creó el interés 'Gastronomía'."))
        except Exception as e:
             self.stdout.write(self.style.ERROR(f"  [FALLO] Error al verificar intereses: {e}"))

        # =================================================================
        # PASO 5: VERIFICAR CACHÉ
        # =================================================================
        self.stdout.write(self.style.NOTICE("PASO 5: Verificando invalidación de Caché..."))
        
        cached_vector = cache.get(cache_key)
        if cached_vector is None:
            self.stdout.write(self.style.SUCCESS("  [ÉXITO] El caché del vector de usuario fue invalidado."))
        else:
            self.stdout.write(self.style.ERROR("  [FALLO] El caché del vector de usuario NO fue invalidado."))
            
        self.stdout.write(self.style.NOTICE("--- Prueba Finalizada ---"))